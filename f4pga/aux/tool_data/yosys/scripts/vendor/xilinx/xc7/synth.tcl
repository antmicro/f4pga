# Copyright (C) 2019-2022 F4PGA Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

yosys -import

plugin -i xdc
plugin -i fasm
plugin -i params
plugin -i sdc
plugin -i design_introspection

# Import the commands from the plugins to the tcl interpreter
yosys -import

source [file join [file normalize [info script]] .. utils.tcl]

# Set-up f4pga input-output metadata (dry run)
f4pga value     top
f4pga value     use_roi
f4pga value     part_name
f4pga value     prjxray_db
f4pga value     bitstream_device
f4pga value     python3
f4pga value     shareDir
f4pga value     yosys_plugins?
f4pga value     surelog_cmd?
f4pga value     extra_techmaps_path?
f4pga value     simulation_models
f4pga value     techmap
f4pga tempfile  json_carry_fixup
f4pga tempfile  json_carry_fixup_out
f4pga take      sources
f4pga take      xdc?
f4pga take      build_dir
f4pga produce   fasm_extra            ${f4pga_build_dir}/${f4pga_top}_extra.fasm       -meta "Extra fasm for pre-configuration of FPGA"
f4pga produce   synth_v               ${f4pga_build_dir}/${f4pga_top}_premap.v         -meta "Pre-technology mapped structural verilog"
f4pga produce   sdc                   ${f4pga_build_dir}/${f4pga_part_name}.sdc        -meta "Standard design constraints"
f4pga produce   json                  ${f4pga_build_dir}/${f4pga_top}.json             -meta "Yosys JSON netlist"
f4pga produce   rtlil_preopt          ${f4pga_build_dir}/${f4pga_top}.pre_abc9.ilang   -meta "Yosys RTLIL file (before optimization)"
f4pga produce   rtlil                 ${f4pga_build_dir}/${f4pga_top}.post_abc9.ilang  -meta "Yosys RTLIL file"

set extra_techmaps_path ${f4pga_extra_techmaps_path}
if { ${extra_techmaps_path} eq "" } {
    set extra_techmaps_path ${f4pga_shareDir}/techmaps/xc7_vpr/techmap
}
set utils_path ${f4pga_shareDir}/scripts

if { [contains $f4pga_yosys_plugins uhdm] } {
    foreach {sysverilog_source} $f4pga_sources {
        read_verilog_with_uhdm $surelog_cmd $sysverilog_source
    }
} else {
    foreach {verilog_source} $f4pga_sources {
        read_verilog $verilog_source
    }
}

# -flatten is used to ensure that the output eblif has only one module.
# Some of symbiflow expects eblifs with only one module.
#
# To solve the carry chain congestion at the output, the synthesis step
# needs to be executed two times.
# abc9 seems to cause troubles if called multiple times in the flow, therefore
# it gets called only at the last synthesis step
#
# Do not infer IOBs for targets that use a ROI.
if { $f4pga_use_roi == "TRUE" } {
    synth_xilinx -flatten -nosrl -noclkbuf -nodsp -noiopad -nowidelut
} else {
    # Read Yosys baseline library first.
    read_verilog -lib -specify +/xilinx/cells_sim.v
    read_verilog -lib +/xilinx/cells_xtra.v

    # Overwrite some models (e.g. IBUF with more parameters)
    read_verilog -lib ${extra_techmaps_path}/iobs.v

    # TODO: This should eventually end up in upstream Yosys
    #       as models such as FD are not currently supported
    #       as being used in old FPGAs (e.g. Spartan6)
    # Read in unsupported models
    read_verilog -lib ${extra_techmaps_path}/retarget.v

    if { $f4pga_top != "" } {
        hierarchy -check -top $f4pga_top
    } else {
        hierarchy -check -auto-top
    }

    # Start flow after library reading
    synth_xilinx -flatten -nosrl -noclkbuf -nodsp -iopad -nowidelut -run prepare:check
}

# Check that post-synthesis cells match libraries.
hierarchy -check

set part_json ${f4pga_prjxray_db}/${f4pga_bitstream_device}/${f4pga_part_name}/part.json

if { $f4pga_xdc != "" } {
  read_xdc -part_json $part_json {*}$f4pga_xdc
  write_fasm -part_json $part_json $f4pga_fasm_extra

  # Perform clock propagation based on the information from the XDC commands
  propagate_clocks
} else {
    # Write empty fasm_extra, to satisfy fasm_extra product
    write_file $f4pga_fasm_extra <<EOT EOT
}

update_pll_and_mmcm_params

# Write the SDC file
#
# Note that write_sdc and the SDC plugin holds live pointers to RTLIL objects.
# If Yosys mutates those objects (e.g. destroys them), the SDC plugin will
# segfault.
write_sdc -include_propagated_clocks $f4pga_sdc

write_verilog $f4pga_synth_v

# Look for connections OSERDESE2.OQ -> OBUFDS.I. Annotate OBUFDS with a parameter
# indicating that it is connected to an OSERDESE2
select -set obufds t:OSERDESE2 %co2:+\[OQ,I\] t:OBUFDS t:OBUFTDS %u  %i
setparam -set HAS_OSERDES 1 @obufds

# Map Xilinx tech library to 7-series VPR tech library.
read_verilog -specify -lib ${f4pga_simulation_models}

# Convert congested CARRY4 outputs to LUTs.
#
# This is required because VPR cannot reliably resolve SLICE[LM] output
# congestion when both O and CO outputs are used. For this reason if both O
# and CO outputs are used, the CO output is computed using a LUT.
#
# Ideally VPR would resolve the congestion in one of the following ways:
#
#  - If either O or CO are registered in a FF, then no output
#    congestion exists if the O or CO FF is packed into the same cluster.
#    The register output will used the [ABCD]Q output, and the unregistered
#    output will used the [ABCD]MUX.
#
#  - If neither the O or CO are registered in a FF, then the [ABCD]Q output
#    can still be used if the FF is placed into "transparent latch" mode.
#    VPR can express this edge, but because using a FF in "transparent latch"
#    mode requires running specific CE and SR signals connected to constants,
#    VPR cannot easily (or at all) express this packing situation.
#
#    VPR's packer in theory could be expanded to express this kind of
#    situation.
#
#                                   CLE Row
#
# +--------------------------------------------------------------------------+
# |                                                                          |
# |                                                                          |
# |                                               +---+                      |
# |                                               |    +                     |
# |                                               |     +                    |
# |                                     +-------->+ O    +                   |
# |              CO CHAIN               |         |       +                  |
# |                                     |         |       +---------------------> xMUX
# |                 ^                   |   +---->+ CO    +                  |
# |                 |                   |   |     |      +                   |
# |                 |                   |   |     |     +                    |
# |       +---------+----------+        |   |     |    +                     |
# |       |                    |        |   |     +---+                      |
# |       |     CARRY ROW      |        |   |                                |
# |  +--->+ S              O   +--------+   |       xOUTMUX                  |
# |       |                    |        |   |                                |
# |       |                    |        +   |                                |
# |  +--->+ DI             CO  +-------+o+--+                                |
# |       |      CI CHAIN      |        +   |                                |
# |       |                    |        |   |                                |
# |       +---------+----------+        |   |       xFFMUX                   |
# |                 ^                   |   |                                |
# |                 |                   |   |     +---+                      |
# |                 +                   |   |     |    +                     |
# |                                     |   +     |     +    +-----------+   |
# |                                     +--+o+--->+ O    +   |           |   |
# |                                         +     |       +  |    xFF    |   |
# |                                         |     |       +->--D----   Q +------> xQ
# |                                         |     |       +  |           |   |
# |                                         +---->+ CO   +   |           |   |
# |                                               |     +    +-----------+   |
# |                                               |    +                     |
# |                                               +---+                      |
# |                                                                          |
# |                                                                          |
# +--------------------------------------------------------------------------+
#

techmap -map ${extra_techmaps_path}/carry_map.v

clean_processes
write_json ${f4pga_json_carry_fixup}

exec $f4pga_python3 ${utils_path}/fix_xc7_carry.py < ${f4pga_json_carry_fixup} > ${f4pga_json_carry_fixup_out}
design -push
read_json ${f4pga_json_carry_fixup_out}

techmap -map ${extra_techmaps_path}/clean_carry_map.v

# Re-read baseline libraries
read_verilog -lib -specify +/xilinx/cells_sim.v
read_verilog -lib +/xilinx/cells_xtra.v
read_verilog -specify -lib ${f4pga_simulation_models}
if { $f4pga_use_roi != "TRUE" } {
    read_verilog -lib ${extra_techmaps_path}/iobs.v
}

# Re-run optimization flow to absorb carry modifications
hierarchy -check

write_ilang $f4pga_rtlil_preopt
if { $f4pga_use_roi == "TRUE" } {
    synth_xilinx -flatten -abc9 -nosrl -noclkbuf -nodsp -noiopad -nowidelut -run map_ffs:check
} else {
    synth_xilinx -flatten -abc9 -nosrl -noclkbuf -nodsp -iopad -nowidelut -run map_ffs:check
}

write_ilang $f4pga_rtlil

# Either the JSON bounce or ABC9 pass causes the CARRY4_VPR CIN/CYINIT pins
# to have 0's when unused.  As a result VPR will attempt to route a 0 to those
# ports. However this is not generally possible or desirable.
#
# The techmap has a simple pass where these unused ports are removed.
# In theory yosys's "rmports" would work here, but
# it does not.
chtype -map CARRY4_VPR CARRY4_FIX
techmap -map  ${f4pga_techmap}

# opt_expr -undriven makes sure all nets are driven, if only by the $undef
# net.
opt_expr -undriven
opt_clean

setundef -zero -params
stat

# TODO: remove this as soon as new VTR master+wip is pushed: https://github.com/SymbiFlow/vtr-verilog-to-routing/pull/525
attrmap -remove hdlname

# Write the design in JSON format.
clean_processes
write_json $f4pga_json
# Write the design in Verilog format.
write_verilog $f4pga_synth_v

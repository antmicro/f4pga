#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2022 F4PGA Authors
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

from colorama import Style
from f4pga.flows.flow_config import FlowDefinition
from pathlib import Path

from f4pga.flows.module import Module
from f4pga.flows.common import decompose_depname

ROOT = Path(__file__).resolve().parent


def _get_if_qualifier(deplist: "list[str]", qualifier: str):
    for dep_name in deplist:
        name, q = decompose_depname(dep_name)
        if q == qualifier:
            yield f"● {Style.BRIGHT}{name}{Style.RESET_ALL}"


def _list_if_qualifier(deplist: "list[str]", qualifier: str, indent: int = 4):
    indent_str = "".join([" " for _ in range(0, indent)])
    r = ""

    for line in _get_if_qualifier(deplist, qualifier):
        r += indent_str + line + "\n"

    return r


def get_module_info(module: Module) -> str:
    r = ""
    r += f"Module `{Style.BRIGHT}{module.name}{Style.RESET_ALL}`:\n"
    r += "Inputs:\n  Required:\n    Dependencies\n"
    r += _list_if_qualifier(module.takes, "req", indent=6)
    r += "    Values:\n"
    r += _list_if_qualifier(module.values, "req", indent=6)
    r += "  Optional:\n    Dependencies:\n"
    r += _list_if_qualifier(module.takes, "maybe", indent=6)
    r += "    Values:\n"
    r += _list_if_qualifier(module.values, "maybe", indent=6)
    r += "Outputs:\n  Guaranteed:\n"
    r += _list_if_qualifier(module.produces, "req", indent=4)
    r += "  On-demand:\n"
    r += _list_if_qualifier(module.produces, "demand", indent=4)
    r += "  Not guaranteed:\n"
    r += _list_if_qualifier(module.produces, "maybe", indent=4)

    return r

def _make_io_dict(io: str, metas: "None | dict[str]" = None) -> "dict[str, str]":
    name, q = decompose_depname(io)
    d = { "qualifier": q }
    if metas is not None:
        meta = metas.get(name)
        if meta is not None:
            d["meta"] = meta
    return name, d

def _make_io_dict_dict(ios: "list[str]", metas: "None | dict[str]" = None) -> "dict[str, str]":
    return dict(_make_io_dict(io, metas) for io in ios)

def _get_module_info_dict(module: Module) -> "dict[str, dict[str, str]]":
    return {
        "takes": _make_io_dict_dict(module.takes),
        "produces": _make_io_dict_dict(
            module.produces,
            metas=module.prod_meta if hasattr(module, 'prod_meta') else None
        ),
        "values": _make_io_dict_dict(module.produces)
    }

def get_stages_info_dict(flow_definition: FlowDefinition) -> "dict[str, dict[str, dict[str, str]]]":
    d = {}
    for stage_name, stage in flow_definition.stages.items():
        d[stage_name] = _get_module_info_dict(stage.module)
    return d

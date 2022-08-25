#!/usr/bin/env bash

# Copyright (C) 2020-2022 F4PGA Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

set -e


echo '::group::Install dependencies'

sudo apt update -y
sudo apt install -y git wget xz-utils

echo '::endgroup::'


echo '::group::Environment variables'

FPGA_FAM="${FPGA_FAM:=xc7}"
F4PGA_INSTALL_DIR="${F4PGA_INSTALL_DIR:=/opt/f4pga}"
F4PGA_INSTALL_DIR_FAM="${F4PGA_INSTALL_DIR}/${FPGA_FAM}"

echo "FPGA_FAM: $FPGA_FAM"
echo "F4PGA_INSTALL_DIR: $F4PGA_INSTALL_DIR"
echo "F4PGA_INSTALL_DIR_FAM: $F4PGA_INSTALL_DIR_FAM"

echo '::endgroup::'


echo '::group::Install Miniconda3'

wget https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh -O conda_installer.sh

bash conda_installer.sh -u -b -p "${F4PGA_INSTALL_DIR_FAM}"/conda
source "${F4PGA_INSTALL_DIR_FAM}"/conda/etc/profile.d/conda.sh

echo '::endgroup::'


echo '::group::Install arch-defs'

mkdir -p "$F4PGA_INSTALL_DIR_FAM"

F4PGA_HASH='674771c'

case "$FPGA_FAM" in
  xc7)    PACKAGES='install-xc7 xc7a50t_test';;
  eos-s3) PACKAGES='install-ql ql-eos-s3_wlcsp';;
  *)
    echo "Unknowd FPGA_FAM <${FPGA_FAM}>!"
    exit 1
esac

for PKG in $PACKAGES; do
    tar -xvf test_pkgs/symbiflow-arch-defs-${PKG}-${F4PGA_HASH}.tar.xz -C $F4PGA_INSTALL_DIR_FAM
done

echo '::endgroup::'


echo '::group::Create environment'

conda env create -f $F4PGA_INSTALL_DIR_FAM/"$FPGA_FAM"_env/"$FPGA_FAM"_environment.yml

echo '::endgroup::'

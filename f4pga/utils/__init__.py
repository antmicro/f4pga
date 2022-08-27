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

from f4pga.utils.xc7.create_place_constraints import main as xc7_create_place_constraints
from f4pga.utils.pp3.create_place_constraints import main as pp3_create_place_constraints

from f4pga.context import FPGA_FAM

if FPGA_FAM == "xc7":
    create_place_constraints = xc7_create_place_constraints
elif F4PGA_FAM == "eos-s3":
    create_place_constraints = pp3_create_place_constraints

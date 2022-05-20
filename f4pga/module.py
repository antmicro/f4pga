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

"""
Here are the things necessary to write an F4PGA Module.
"""

from types import SimpleNamespace
from abc import abstractmethod

from f4pga.common import (
    decompose_depname,
    ResolutionEnv
)


class Module:
    """
    A `Module` is a wrapper for whatever tool is used in a flow.
    Modules can request dependencies, values and are guranteed to have all the required ones present when entering
    `exec` mode.
    They also have to specify what dependencies they produce and create the files for these dependencies.
    """

    no_of_phases: int
    name: str
    takes: 'list[str]'
    produces: 'list[str]'
    values: 'list[str]'
    prod_meta: 'dict[str, str]'

    @abstractmethod
    def execute(self, ctx):
        """
        Executes module.
        Use yield to print a message informing about current execution phase.
        `ctx` is `ModuleContext`.
        """
        pass

    @abstractmethod
    def map_io(self, ctx) -> 'dict[str, ]':
        """
        Returns paths for outputs derived from given inputs.
        `ctx` is `ModuleContext`.
        """
        pass

    def __init__(self, params: 'dict[str, ]'):
        self.no_of_phases = 0
        self.current_phase = 0
        self.name = '<BASE STAGE>'
        self.prod_meta = {}


class ModuleContext:
    """
    A class for object holding mappings for dependencies and values as well as other information needed during modules
    execution.
    """

    share: str                 #  Absolute path to F4PGA's share directory
    bin: str                   #  Absolute path to F4PGA's bin directory
    takes: SimpleNamespace     #  Maps symbolic dependency names to relative paths.
    produces: SimpleNamespace  #  Contains mappings for explicitely specified dependencies.
                               #  Useful mostly for checking for on-demand optional outputs (such as logs) with
                               #    `is_output_explicit` method.
    outputs: SimpleNamespace   #  Contains mappings for all available outputs.
    values: SimpleNamespace    #  Contains all available requested values.
    r_env: ResolutionEnv       # `ResolutionEnvironmet` object holding mappings for current scope.
    module_name: str           # Name of the module.

    def is_output_explicit(self, name: str):
        """
        True if user has explicitely specified output's path.
        """
        return getattr(self.produces, name) is not None

    def _getreqmaybe(self, obj, deps: 'list[str]', deps_cfg: 'dict[str, ]'):
        """
        Add attribute for a dependency or panic if a required dependency has not been given to the module on its input.
        """
        for name in deps:
            name, spec = decompose_depname(name)
            value = deps_cfg.get(name)
            if value is None and spec == 'req':
                fatal(-1, f'Dependency `{name}` is required by module `{self.module_name}` but wasn\'t provided')
            setattr(obj, name, self.r_env.resolve(value))

    # `config` should be a dictionary given as modules input.
    def __init__(
        self,
        module: Module,
        config: 'dict[str, ]',
        r_env: ResolutionEnv,
        share: str,
        bin: str
    ):
        self.module_name = module.name
        self.takes = SimpleNamespace()
        self.produces = SimpleNamespace()
        self.values = SimpleNamespace()
        self.outputs = SimpleNamespace()
        self.r_env = r_env
        self.share = share
        self.bin = bin

        self._getreqmaybe(self.takes, module.takes, config['takes'])
        self._getreqmaybe(self.values, module.values, config['values'])

        produces_resolved = self.r_env.resolve(config['produces'])
        for name, value in produces_resolved.items():
            setattr(self.produces, name, value)

        outputs = module.map_io(self)
        outputs.update(produces_resolved)

        self._getreqmaybe(self.outputs, module.produces, outputs)

    def shallow_copy(self):
        cls = type(self)
        mycopy = cls.__new__(cls)

        mycopy.module_name = self.module_name
        mycopy.takes = self.takes
        mycopy.produces = self.produces
        mycopy.values = self.values
        mycopy.outputs = self.outputs
        mycopy.r_env = self.r_env
        mycopy.share = self.share
        mycopy.bin = self.bin

        return mycopy


class ModuleRuntimeException(Exception):
    info: str

    def __init__(self, info: str):
        self.info = info

    def __str___(self):
        return self.info


def get_mod_metadata(module: Module):
    """
    Get descriptions for produced dependencies.
    """
    meta = {}
    has_meta = hasattr(module, 'prod_meta')
    for prod in module.produces:
        prod = prod.replace('?', '').replace('!', '')
        if not has_meta:
            meta[prod] = '<no descritption>'
            continue
        prod_meta = module.prod_meta.get(prod)
        meta[prod] = prod_meta if prod_meta else '<no description>'
    return meta

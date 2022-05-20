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

from pathlib import Path
from zlib import adler32 as zlib_adler32
from json import dump as json_dump, load as json_load, JSONDecodeError


class SymbiCache:
    """
    `SymbiCache` is used to track changes among dependencies and keep the status of the files on a persistent storage.
    Files which are tracked get their checksums calculated and stored in a file.
    If file's checksum differs from the one saved in a file, that means, the file has changed.
    """

    hashes: 'dict[str, dict[str, str]]'
    status: 'dict[str, str]'
    cachefile_path: str

    def __init__(self, cachefile_path):
        """
        `chachefile_path` - path to a file used for persistent storage of checksums.
        """

        self.status = {}
        self.cachefile_path = cachefile_path
        self.load()

    def _try_pop_consumer(self, path: str, consumer: str):
        if self.status.get(path) and self.status[path].get(consumer):
            self.status[path].pop(consumer)
            if len(self.status[path]) == 0:
                self.status.pop(path)
        if self.hashes.get(path) and self.hashes[path].get(consumer):
            self.hashes[path].pop(consumer)
            if len(self.hashes[path]) == 0:
                self.hashes.pop(path)

    def _try_push_consumer_hash(self, path: str, consumer: str, hash):
        if not self.hashes.get(path):
            self.hashes[path] = {}
        self.hashes[path][consumer] = hash
    def _try_push_consumer_status(self, path: str, consumer: str, status):
        if not self.status.get(path):
            self.status[path] = {}
        self.status[path][consumer] = status

    def update(self, path: str, consumer: str):
        """ Add/remove a file to.from the tracked files, update checksum if necessary and calculate status.

        Multiple hashes are stored per file, one for each consumer module.
        "__target" is used as a convention for a "fake" consumer in case the file is requested as a target and not used
        by a module within the active flow.
        """

        isdir = Path(path).is_dir()
        if not (Path(path).is_file() or Path(path).is_symlink() or isdir):
            self._try_pop_consumer(path, consumer)
            return True
        hash = 0 # Directories always get '0' hash.
        if not isdir:
            with Path(path).open('rb') as rfptr:
                hash = str(zlib_adler32(rfptr.read()))

        last_hashes = self.hashes.get(path)
        last_hash = None if last_hashes is None else last_hashes.get(consumer)

        if hash != last_hash:
            self._try_push_consumer_status(path, consumer, 'changed')
            self._try_push_consumer_hash(path, consumer, hash)
            return True
        self._try_push_consumer_status(path, consumer, 'same')
        return False

    def get_status(self, path: str, consumer: str):
        """ Get status for a file with a given path.
        returns 'untracked' if the file is not tracked or hasn't been treated with `update` procedure before calling
        `get_status`.
        """
        statuses = self.status.get(path)
        if not statuses:
            return 'untracked'
        status = statuses.get(consumer)
        if not status:
            return 'untracked'
        return status

    def load(self):
        """Loads cache's state from the persistent storage"""

        try:
            with Path(self.cachefile_path).open('r') as rfptr:
                self.hashes = json_load(rfptr)
        except JSONDecodeError as jerr:
            print("""WARNING: .symbicache is corrupted!
This will cause flow to re-execute from the beggining.""")
            self.hashes = {}
        except FileNotFoundError:
            print("""Couldn\'t open .symbicache cache file.
This will cause flow to re-execute from the beggining.""")
            self.hashes = {}

    def save(self):
        """Saves cache's state to the persistent storage."""
        with Path(self.cachefile_path).open('w') as wfptr:
            json_dump(str(self.hashes), wfptr, indent=4)

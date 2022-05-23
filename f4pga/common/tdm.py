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

import argparse
from platform import platform
import requests
import re
from datetime import datetime

class Config:
    def __init__(self, project: str = 'symbiflow-arch-defs',
                 build_name: str = 'install', jobset: str = 'continuous'):
        self.project = project
        self.build_name = build_name
        self.jobset = jobset

class ArtifactRef:
    def __init__(self, id: str, name: str, url: str, size: int, content_type: str,
                 timestamp: datetime, build_id: str):
        self.id = id
        self.name = name
        self.url = url
        self.size = size
        self.content_type = content_type
        self.timestamp = timestamp
        self.build_id = build_id
    
    def __repr__(self) -> str:
        return 'ArtifactRef { ' + f'"{self.name}" ({self.size}B): {self.url}' + ' }'

class BuildRef:
    def __init__(self, timestamp: datetime, install: ArtifactRef,
                 platform_artifacts: 'dict[str, ArtifactRef] | None' = None):
        self.timestamp = timestamp
        self.install = install
        if platform_artifacts is not None:
            self.platform_artifacts = platform_artifacts
        else:
            self.platform_artifacts = {}



def extract_bhash(name: str):
    m = re.match('[^.]*-([^.-]*)(\\..*)?', name)
    if m:
        return m.groups()[0]
    return None

# For now we use only `symbiflow-arch-defs` and download tarballs
def get_latest_artifact_refs(cfg: Config) -> 'tuple[list[ArtifactRef], str]':
    # Handle case in which there is build_name is absent
    build_name: str
    if cfg.build_name:
        build_name = f'/{cfg.build_name}'
    else:
        build_name = ''

    base_url = f'https://www.googleapis.com/storage/v1/b/{cfg.project}/o'
    prefix = f'artifacts/prod/foss-fpga-tools/{cfg.project}/{cfg.jobset}{build_name}/'
    params = {'prefix': prefix}
    artifacts = []

    to_strip = f'{cfg.project}/{prefix}'

    while True:
        r = requests.get(
            base_url,
            params=params,
            headers={'Content-Type': 'application/json'},
        )
        r.raise_for_status()

        try:
            items = r.json()['items']
        except KeyError as e:
            print(e)
            return [], ''

        for obj in items:
            obj_id = obj['id'].replace(to_strip, '').split('/')[0]
            artifact_name = obj['selfLink'].split('%2F')[-1]
            artifacts += [ArtifactRef(
                id=obj_id,
                name=artifact_name,
                url=obj['mediaLink'],
                size=int(obj['size']),
                content_type=obj['contentType'],
                timestamp=datetime.strptime(obj['updated'], '%Y-%m-%dT%H:%M:%S.%fZ'),
                build_id=extract_bhash(artifact_name)
            )]

        try:
            params['pageToken'] = r.json()['nextPageToken']
        except KeyError:
            break

    try:
        build_no = max([a.id for a in artifacts])
    except ValueError as e:
        print(e)
        return [], ''

    return artifacts, build_no

def _nop(*args, **kwargs):
    pass

def prog(d, total):
    print(f'{d}B / {total}B')

def download(artifact_ref: ArtifactRef, destination: str, chunk_size: int = 1024,
             report_progress = _nop):
    slash_pos = artifact_ref.content_type.find('/')
    if slash_pos == -1:
        raise RuntimeError(f'Invalid/Unsupported content type {artifact_ref.content_type} '
                           f'for artifact {artifact_ref.name}')
    content_kind = artifact_ref.content_type[:slash_pos]
    binary = content_kind != 'text'
    
    if binary:
        count = artifact_ref.size / chunk_size + 1
        report_progress(0, count * chunk_size)
        resp = requests.get(url=artifact_ref.url,
                            headers={"Content-Type": artifact_ref.content_type},
                            stream=True)
        resp.raise_for_status()
        chunks = resp.iter_content(chunk_size)

        with open(destination, 'wb') as f:
            for idx, chunk in enumerate(chunks):
                if not chunk:
                    raise RuntimeError(f'Failed to download artifact {artifact_ref.name}')
                f.write(chunk)
                report_progress(idx * chunk_size, count * chunk_size)
            f.flush()
    else:
        report_progress(0, artifact_ref.size)
        resp = requests.get(url=artifact_ref.url,
                        headers={"Content-Type": artifact_ref.content_type})
        resp.raise_for_status()

        with open(destination, 'w') as f:
            f.write(resp.text)
            f.flush()
        report_progress(artifact_ref.size, artifact_ref.size)

def detect_builds(config: Config, artifact_refs: 'list[ArtifactRef]'):
    build_aref_map = {}
    build_pkg_arefs = []
    for aref in artifact_refs:
        m1 = re.match(f'^{config.project}-{config.build_name}', aref.name)
        if m1 is not None:
            build_pkg_arefs += [aref]
        else:
            if build_aref_map.get(aref.build_id) is None:
                build_aref_map[aref.build_id] = []
            build_aref_map[aref.build_id] += [aref]

    for build_pkg_aref in build_pkg_arefs:
        build_ref = BuildRef(build_pkg_aref.timestamp, build_pkg_aref)
        build_platfrom_arefs = build_aref_map.get(build_pkg_aref.build_id)
        if build_platfrom_arefs is None:
            continue
        for aref in build_platfrom_arefs:
            m2 = re.match(f'{config.project}-([^.]*)-([^.-]*)(\\..*)?', aref.name)
            if m2 is not None:
                platform_name = m2.groups()[0]
                build_ref.platform_artifacts[platform_name] = aref
        
        yield build_ref

def list_builds(config: Config, limit = 999):
    arefs = get_latest_artifact_refs(config)[0]
    build_refs = sorted(detect_builds(config, arefs), key=lambda br: br.timestamp,
                        reverse=True)
    for idx, bref in enumerate(build_refs):
        if idx >= limit:
            print('...')
            break

        name = ''
        if idx == 0:
            name += '(latest) '
        name += str(bref.timestamp)

        print(f'{idx}: {name}')
        for platform_name, _ in bref.platform_artifacts.items():
            print(f'  * {platform_name}')


def main():
    parser = argparse.ArgumentParser(
        description='Retrieves the latest artifacts of SymbiFlow-related CIs.'
    )

    parser.add_argument(
        '--project',
        default='symbiflow-arch-defs',
        help='Name of the SymbiFlow project',
    )
    parser.add_argument(
        '--build_name',
        default='install',
        help='Name of the CI that produced the artifact',
    )
    parser.add_argument(
        '--jobset',
        default='continuous',
        help='Name of the jobset. Can choose between presubmit and continous',
    )
    parser.add_argument(
        '--get_build_number',
        action='store_true',
        help='Retrieve the CI build number',
    )
    parser.add_argument(
        '--get_single_url',
        action='store_true',
        help='Retrieve a single random URL from a given build',
    )
    parser.add_argument(
        '--get_all_urls',
        action='store_true',
        help='Retrieve all the URLs of a given build',
    )

    args = parser.parse_args()

    # Default to use get_single_url if none of the options is selected
    if not (args.get_all_urls or args.get_single_url or args.get_build_number):
        args.get_single_url = True

    if args.get_build_number:
        assert not (args.get_all_urls or args.get_single_url)
        _, build_number = get_latest_artifact_refs(
            Config(args.project, args.build_name, args.jobset)
        )
        print(build_number)

    elif args.get_all_urls:
        assert not (args.get_build_number or args.get_single_url)
        artifacts, _ = get_latest_artifact_refs(
            Config(args.project, args.build_name, args.jobset)
        )
        for a in artifacts:
            print(f'"{a.name}": {a.url}')

    elif args.get_single_url:
        assert not (args.get_build_number or args.get_all_urls)
        artifacts, _ = get_latest_artifact_refs(
            Config(args.project, args.build_name, args.jobset)
        )
        print(f'"{artifacts[0].name}, {artifacts[0].content_type}": {artifacts[0].url}')


if __name__ == '__main__':
    main()

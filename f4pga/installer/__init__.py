import os
import shutil
from pathlib import Path
import tarfile
import shlex
from subprocess import run
import re

from f4pga.common import tdm

_F4PGA_INSTALL_PATH_ENV_VAR = 'F4PGA_INSTALL_PATH'
_F4PGA_CONDA_ENV_NAME = 'f4pga_arch_def_base'
_F4PGA_DEFAULT_PYTHON = '3.9'

def get_install_path() -> 'str | None':
    return os.environ.get(_F4PGA_INSTALL_PATH_ENV_VAR)

def get_conda_path() -> 'str | None':
    return shutil.which('conda')

def install_conda(path):
    raise RuntimeError('Autoatic Conda installation is not currently implemented')

def create_portable_root(path: Path):
    os.mkdir(path.as_posix())
    os.mkdir(path.joinpath('archdefs'))

def get_artifact_path(destination: Path, aref: tdm.ArtifactRef):
    return destination.joinpath(aref.name)

def download_build_data(destination: Path, build_ref: tdm.BuildRef,
                        platforms: 'list[str]'):
    chunk_sz = 10 * 1024 * 1024 # Report progress every 10MB
    def prog(d, total):
        print(f'  downloaded {d}B / {total}B')
    
    install_path = get_artifact_path(destination, build_ref.install)
    
    print('Downloading installation data...')
    tdm.download(build_ref.install, str(install_path), chunk_sz, prog)
    
    for platform_name in platforms:
        aref = build_ref.platform_artifacts.get(platform_name)
        if aref is None:
            print(f'No downloads found for platform {platform_name}!')
            continue
        print(f'Downloading platform data for {platform_name}...')
        tdm.download(aref, str(Path(destination).joinpath(aref.name)), chunk_sz, prog)

def clean_install_arch_garbage(install_dir: Path):
    garbage_arch = install_dir.joinpath('share/symbiflow/arch')
    if garbage_arch.exists():
        shutil.rmtree(garbage_arch)


def install_downloaded_data(downloads: Path, install_dir: Path,
                            build_ref: tdm.BuildRef, platforms: 'list[str]'):
    print('Installing main components...')
    install_tar_path = get_artifact_path(downloads, build_ref.install)
    install_tar = tarfile.open(name=str(install_tar_path), mode='r:xz')
    install_tar.extractall(install_dir)
    #shutil.move(install_dir.joinpath('install'), install_dir)
    clean_install_arch_garbage(install_dir)
    install_dir.joinpath('share/symbiflow/arch').mkdir()
    
    arch_dir = install_dir.joinpath('share/symbiflow/arch')
    
    for platform_name in platforms:
        aref = build_ref.platform_artifacts.get(platform_name)
        if aref is None:
            print(f'No downloads found for platform {platform_name}!')
            continue
        
        print(f'Installing platform data for {platform_name}...')
        extract_path = downloads.joinpath(aref.name + '_extracted')
        extract_path.mkdir()
        platform_tar_path = downloads.joinpath(aref.name)
        platform_tar = tarfile.open(name=str(platform_tar_path), mode='r:xz')
        platform_tar.extractall(extract_path)
        arch_path = extract_path.joinpath(f'share/symbiflow/arch/{platform_name}')
        shutil.move(arch_path, arch_dir)
        shutil.rmtree(extract_path)

def get_builds():
    config = tdm.Config()
    arefs = tdm.get_latest_artifact_refs(config)[0]
    brefs = tdm.detect_builds(config, arefs)
    return sorted(brefs, key=lambda bref: bref.timestamp, reverse=True)

def select_build_dialog(builds: 'list[tdm.BuildRef]', show_max: int = 3):
    print('Select desired build: ')

    show_offset = 0

    build_idx = 0
    while True:
        max_id = min(show_offset + show_max, len(builds))
        choice_id = 1

        allow_next_page = (show_offset >= 0) and show_offset + (show_max) < len(builds)
        allow_prev_page = show_offset > 0

        for idx in range(show_offset, max_id ):
            build_ref = builds[idx]
            build_name = ''
            if idx == 0:
                build_name += '(latest) '
            build_name += str(build_ref.timestamp)

            print(f'#{choice_id}: {build_name}\n    Available platforms:')
            for platform_name in sorted(build_ref.platform_artifacts.keys()):
                print(f'    * {platform_name}')

            choice_id += 1
        
        if allow_next_page:
            print('#> next page')
        if allow_prev_page:
            print('#< previous page')
        
        chid = input('Please choose you build: ')
        if chid == '>':
            if allow_next_page:
                show_offset += show_max
            continue
        if chid == '<':
            if allow_prev_page:
                show_offset -= show_max
            continue
        
        try:
            build_idx = show_offset + int(chid) - 1
        except:
            print('Wrong input.')
            continue
        break

    build_ref = builds[build_idx]

    print('Please select platforms you want to use:')

    sorted_platform_names = sorted(build_ref.platform_artifacts.keys())
    selected_platforms = set()
    while True:
        choice_id = 1
        for platform_name in sorted_platform_names:
            marker = '[*]' if platform_name in selected_platforms else '[ ]'
            print(f'{marker} #{choice_id}: {platform_name}')
            choice_id += 1
        print('#y: confirm selection')
        selection = input('Choice: ')

        if selection == 'y':
            break

        try:
            chid = int(selection)
        except:
            print('Wrong input')
            continue

        if (chid <= 0) or (chid > len(sorted_platform_names)):
            print('Wrong input')
            continue
        
        platform_name = sorted_platform_names[chid - 1]

        if platform_name in selected_platforms:
            selected_platforms.remove(platform_name)
        else:
            selected_platforms.add(platform_name)
    
    return build_ref, selected_platforms

def write_settings_file(install_path: Path) -> Path:
    name = 'settings.sh'
    script = f'export {_F4PGA_INSTALL_PATH_ENV_VAR}={shlex.quote(install_path)}\n' \
             f'conda activate {_F4PGA_CONDA_ENV_NAME}'

    settings_path = install_path.joinpath(name)

    with open(settings_path, 'w') as f:
        f.write(script)
    
    return settings_path

def update_conda_env(install_path: Path):
    environment_yml = install_path.joinpath('environment.yml')
    out = run([
        'conda', 'env', 'update',
        '-n', _F4PGA_CONDA_ENV_NAME,
        '--file', environment_yml
    ], capture_output=True)

    if out.returncode != 0:
        print(f'{out.stdout.decode()}\n')
        raise RuntimeError('f4pga: Failed to update conda environment.')

def is_f4pga_env_available():
    out = run(['conda', 'env', 'list'], capture_output=True)
    assert out.returncode == 0
    for line in out.stdout.decode().splitlines():
        m = re.match(f'[ ]*{_F4PGA_CONDA_ENV_NAME}[ ]* .*', line)
        if m is not None:
            return True
    return False

def is_in_f4pga_env():
    out = run(['conda', 'env', 'list'], capture_output=True)
    assert out.returncode == 0
    for line in out.stdout.decode().splitlines():
        m = re.match(f'[ ]*{_F4PGA_CONDA_ENV_NAME}[ ]*\* .*', line)
        if m is not None:
            return True
    return False

def create_f4pga_env():
    out = run([
        'conda', 'env', 'create'
        '-n', _F4PGA_CONDA_ENV_NAME,
        f'python={_F4PGA_DEFAULT_PYTHON}'
    ], capture_output=True)
    assert out.returncode == 0

def create_f4pga_env_dialog():
    while True:
        choice = input('F4PGA conda environment was not detected. Create one? [Y/n] ')
        if (choice == '') or (choice == 'y') or (choice == 'Y'):
            create_f4pga_env()
            
            print( 'Please enter the new environment by typing')
            print(f'  $ conda activate {_F4PGA_CONDA_ENV_NAME}')
            print( 'and run the installer again.')
            exit(0)
        if (choice == 'n') or (choice == 'N'):
            print( 'You can create the environment manually by typing')
            print(f'  $ conda env create -n {_F4PGA_CONDA_ENV_NAME} python={_F4PGA_DEFAULT_PYTHON}')
            print( 'After creating the environment, please enter it by typing')
            print(f'  $ conda activate {_F4PGA_CONDA_ENV_NAME}')
            print( 'and then run the installer again.')
            exit(0)
        
        print('Wrong choice.')

def main():
    print('Welcome to F4PGA installer!\n')

    conda_path = get_conda_path()
    if conda_path is None:
        print('f4pga requires a conda installation.')
        print('Please go to https://docs.conda.io/en/latest/miniconda.html '
              'and follow the instructions.')
        exit(0)
    
    if not is_f4pga_env_available():
        create_f4pga_env_dialog()
    
    if not is_in_f4pga_env():
        print( 'Please enter the f4pga environment by typing')
        print(f'  $ conda activate {_F4PGA_CONDA_ENV_NAME}')
        print( 'and run the installer again.')
        exit(0)

    install_dir = Path(input('Please specify desired installation location: '))

    if install_dir.exists():
        print('Directory already exist.')
        exit(0)
    
    install_dir.mkdir()

    print('Fetching available builds...')
    builds = get_builds()

    build_ref, platforms = select_build_dialog(builds)

    download_tmp = Path('/tmp/f4pga_downloads')
    download_tmp.mkdir()

    try:
        download_build_data(download_tmp, build_ref, platforms)
        install_downloaded_data(download_tmp, install_dir, build_ref, platforms)
    finally:
        print('Cleaning up...')
        shutil.rmtree(download_tmp)
    
    print('Updating conda environment...')
    update_conda_env(install_dir)
    
    settings_path = write_settings_file(install_dir)
    
    print('F4PGA has been installed.')
    print(f'To use f4pga, please source the following file: {settings_path}')

import os, sys, subprocess, shlex
from warnings import simplefilter
from getpass import getpass


host = os.environ['MAC_CLANGD_HOST']
remote_ip = os.environ['MAC_REMOTE_IP']
remote_base = os.environ['MAC_CLANGD_REMOTE_BASE']

if 'MAC_PROJECT_NAME' in os.environ:
    current_project_name = os.environ['MAC_PROJECT_NAME']
else:
    current_project_name = ''

curr_project_local_root = f'Z:\\{current_project_name}'
curr_project_remote_root = f'/Users/sam/SmbShared/{current_project_name}'

if 'MAC_PASSWORD' in os.environ:
    mac_password = os.environ['MAC_PASSWORD']
else:
    mac_password = getpass('Please enter password for remote machine: ')
    os.environ['MAC_PASSWORD'] = mac_password


#normalized path separators to use only sep
def normalize_path(path: str, sep='/'):
    bad_sep = '\\' if sep == '/' else '/'
    return path.replace(bad_sep, sep)

#returns the parent dir of path in the exact same style as path.  Relative or absolute as path is, and same path separator / or \
def parent_dir(path: str):
    sep = '\\'
    if '\\' in path:
        path = path.replace('/', '\\')
    else:
        path = path.replace('\\', '/')
        sep = '/'
    return sep.join(os.path.split(path)[:-1])


def is_z_drive_path(path: str):
    return path.startswith('Z:\\') or path.startswith('Z:/') or path.startswith(remote_ip) or path.startswith(f'\\\\{remote_ip}')

#checks if path is a valid path on a remote share on the mac
def is_valid_remote_path(path: str):
    return path.startswith(remote_base)

#translates a path from something like Z:\MusicVisualizer\audioloopbackstream.h
#to something like /Users/sam/SmbShared/MusicVisualizer/audioloopbackstream.h
def translate_z_to_mac(path: str):
    return path.replace('\\', '/').replace('Z:', remote_base)
    # return path.replace('Z:\\', f'{remote_base}/').replace('\\', '/')

#takes an unmodified local windows path to a shared dir, and returns the absolute mac path to the same location
#currently does not support .. in paths
def to_remote_path(path: str):
    path = normalize_path(path)
    parts = path.split('/')
    cwd = normalize_path(os.getcwd())
    #if there is only a single path component
    if len(parts) == 1:
        if path in os.listdir(cwd):
            path = normalize_path(os.path.join(cwd, path))
            return translate_z_to_mac(path)


    for i, part in enumerate(parts):
        if part == '.':
            parts[i] = cwd

    path = '/'.join(parts)

    if is_z_drive_path(path):
        path = translate_z_to_mac(path)
    else:
        path = normalize_path(path)
        if not is_valid_remote_path(path):
            #we will assume that the path given is a relative path from the current project root dir
            return normalize_path(os.path.join(curr_project_remote_root, path))
            raise RuntimeError(f'Error, cannot convert a local windows path to a remote mac path.  Must be a Z: drive path or a mac path\n\nInvalid path: {path}')
    return path



def get_project_remote_root_path(path: str):
    path = to_remote_path(path)
    curr_path = path
    prev_path = path
    while curr_path != remote_base:
        prev_path = curr_path
        curr_path = parent_dir(curr_path)
    return prev_path


def run_process(args: list[str]) -> str:
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        print(f'Error executing command: {args}\nError text:')
        print(proc.stderr.decode(errors='replace'))
        raise RuntimeError(f'Error executing command: {args}')
    try:
        res = proc.stdout.decode(errors='replace')
    except Exception as e:
        print(f'Exception occured while trying to decode process output for commmand: {args}')
        raise RuntimeError(e)
    return res



def remote_execute(cmd: str, verbose=False) -> str:
    #wrap cmd first in a zsh login call to ensure access to all normal executables
    #then wrap that in a ssh call to the remote host
    prefix = f'security unlock-keychain -p {mac_password} login.keychain && '
    cmd = prefix + cmd
    full_cmd = f"ssh {host} 'zsh -lc \"{cmd}\"'"
    if verbose:
        print(f'Remote executing full_cmd: {full_cmd}')
    args = shlex.split(full_cmd)
    return run_process(args)




#This is a DEAD simple function that makes a ton of assumptions and is incredibly brittle
def simple_remote_cmake(project_name: str = '', build=False):
#ssh mac-clangd 'zsh -lc "cmake --build /Users/sam/SmbShared/ScreenCaptureKitTest/build"' 
    
    if not project_name:
        if not current_project_name:
            raise ValueError('Error, no project name')
        project_name = current_project_name 
    project_root_dir = normalize_path(os.path.join(remote_base, project_name))
    print(f'project_root_dir: {project_root_dir}')

    if build:
        cmd = f"ssh mac-clangd 'zsh -lc \"cmake --build {project_root_dir}/build\"'"
    else:
        cmd = f"ssh mac-clangd 'zsh -lc \"cmake -S {project_root_dir} -B {project_root_dir}/build\"'"

    args = shlex.split(cmd)
    return run_process(args)




def remote_cmake(parsed_args: dict):
    cwd = os.getcwd()
    args = list(parsed_args['argv'])
    short_flags: dict[str, str] = dict(parsed_args['short'])
    long_flags: dict[str, str] = dict(parsed_args['long'])
    plain_args: list[str] = list(parsed_args['args'])

    if 'B' in short_flags:
        build_path = to_remote_path(short_flags['B'])
        if 'S' in short_flags:
            source_path = to_remote_path(short_flags['S'])
        else:
            source_path = to_remote_path(cwd)

        cmd = f"cmake -S {source_path} -B {build_path}"

        # cmd = f'ssh {host} "cmake -S {source_path} -B {build_path}'
        for flag, val in short_flags.items():
            if flag not in ['S', 'B']:
                if val is not None:
                    cmd += f' -{flag} {val}'
                else:
                    cmd += f' -{flag}'

        for flag, val in long_flags.items():
            if val is not None:
                cmd += f' -{flag} {val}'
            else:
                cmd += f' -{flag}'

        print(f'running command: {cmd}')
        # cmd = f"ssh mac-clangd 'zsh -lc \"cmake -S {source_path} -B {build_path}\"'"
        res = remote_execute(cmd)
        print(res)
        return res

    elif 'build' in long_flags:
        build_path = to_remote_path(long_flags['build'])
        print(f'Buildilng build folder at absolute path: {build_path}')
        cmd = f'cmake --build {build_path}'
        res = remote_execute(cmd)
        print(res)
        return res





# if __name__ == '__main__':
#     parsed_args = parse_args(sys.argv)
#     short_flags = parsed_args['short']
#     long_flags = parsed_args['long']
#     plain_args = parsed_args['args']
#     cwd = os.getcwd()
#
#     if plain_args[0] == 'cmake':
#         remote_cmake(parsed_args)
#     exit()
#
#     if len(plain_args) == 0:
#         pass
#
#
#     ssh_host = os.environ['MAC_CLANGD_HOST']
#     project_name = ''#os.environ['MAC_PROJECT_NAME']
#     project_root_path = f'Z:\\{project_name}'
#
#     remote_project_root_path = f'/Users/sam/SmbShared/{project_name}'
#
#     path = 'Z:\\MusicVisualizer\\.git\\whatever\\file.txt'
#
#     print(to_remote_path(sys.argv[1]))
#     exit()
#
#

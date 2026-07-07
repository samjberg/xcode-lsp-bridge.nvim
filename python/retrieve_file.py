import shlex
import os, sys, subprocess
from rdt_utils import *

cwd = os.getcwd()
headers_dir_name = 'remote-header-files'
headers_dir_path = os.path.join(current_project_root_local, headers_dir_name)
headers_dir_path_normed = normalize_path(headers_dir_path)





# Translates a remote header file path such as '/Library/Developer/CommandLineTools.. to the same path joined to the local headers root
# i.e. /Users/{username}/.remote-development-tools/remote-header-files/Library/Developer/CommandLineTools..
# The strip_drive option ONLY forces the drive to be stripped when True.
# Setting it to False does NOT guarantee that there will be a drive part
def path_remote_to_local_header(remote_path: str, strip_drive=True) -> str:
    remote_path = normalize_path(remote_path)
    if remote_path.startswith('/'):
        remote_path = remote_path[1:]
    headers_dir_path_normed = normalize_path(headers_dir_path, strip_drive=strip_drive)
    return normalize_path(os.path.join(headers_dir_path_normed , remote_path))

def retrieve_file(remote_path: str, local_path: str) -> bool:
    if not os.path.exists(local_path):
        local_dir = os.path.split(local_path)[0]
        if not os.path.exists(local_dir):
            raise RuntimeError('Error, {local_path} is not a valid argument.  It must be a path to an existing directory to save to, or a path inside of an existing directory')
    else:
        local_dir = os.path.split(local_path)[0]
        # local_path = os.path.join(local_path, remote_fname)

    if not os.path.isdir(local_dir):
        raise RuntimeError(f'Error, {local_dir} is not an existing directory')

    local_path = normalize_path(os.path.abspath(local_path), strip_drive=True)
    cmd = shlex.split(f'rsync -azP -e /usr/bin/ssh {remote_host}:{remote_path} /c{local_path}')
    subprocess.run(cmd)

    return True


# Retrieves a header file from the remote machine and saves it to the corresponding path rooted in `headers_dir_path`
# For example if the header file is located on /a/b/c/file.h on the remote machine, it would get saved to
# {headers_dir_path}/a/b/c/file.h, while all intermediate directories being created as neccessary automatically
def retrieve_header_file(remote_path: str, use_cached=True) -> str:
    local_path = normalize_path(os.path.join(headers_dir_path, remote_path[1:]), '\\')
    if os.path.exists(local_path) and use_cached:
        log_unmissable(f'RETURNING CACHED HEADER PATH: {local_path}')
        return local_path
    local_dir = os.path.split(local_path)[0]
    if not os.path.exists(local_dir):
        os.makedirs(local_dir)
    retrieve_file(remote_path, local_path)
    return local_path



cwd = os.getcwd()

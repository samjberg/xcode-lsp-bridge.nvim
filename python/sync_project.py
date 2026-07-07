# import subprocess, shlex
import shlex
import subprocess
from rdt_utils import *

# Syncronization directions
PUSH = 'push'
PULL = 'pull'

# as_dir options.  This represents which (if any) paths to treat as a directory, the src, dest, both, or neither.
# Really just for fun, this is used as a bitfield.  The as_dir parameter in certain functions uses of one these values,
# and it is and'ed together with either SRC or DST to determine if it should be treated as a directory or not
NEITHER = 0
SRC = 1
DST = 2
BOTH = 3

cwd = os.getcwd()

def create_local_rsync_arg(path: str, as_dir: bool = True):
    normed_path = normalize_path(path, strip_drive=True)
    local_rsync_path = f'/c{normed_path}'
    local_rsync_path += '/' if as_dir else ''
    return local_rsync_path

def create_remote_rsync_arg(path: str, as_dir: bool = True):
    normed_path = normalize_path(path, strip_drive=True)
    normed_path += '/' if as_dir else ''
    return f'{remote_host}:{normed_path}'


def create_rsync_cmd(local_path: str, remote_path: str, sync_direction=PUSH, local_is_dir=True, remote_is_dir=True):
    # src = create_local_rsync_arg(local_path, local_is_dir) if sync_direction==PUSH else create_remote_rsync_arg(, src_is_dir)
    # dst = create_remote_rsync_arg(dst_path, dst_is_dir) if sync_direction==PUSH else create_local_rsync_arg(dst_path, dst_is_dir)
    local = create_local_rsync_arg(local_path, as_dir=local_is_dir)
    remote = create_remote_rsync_arg(remote_path, as_dir=remote_is_dir)
    base = 'rsync -azP -e /usr/bin/ssh '
    return shlex.split(f'{base} {local} {remote}') if sync_direction==PUSH else shlex.split(f'{base} {remote} {local}')

def sync_project(project_root: str = '', sync_direction=PUSH, dry_run=True):
    if not project_root:
        project_root = current_project_root_local
    remote_project_root = clangd_path_mapping_path(project_root)
    cmd = create_rsync_cmd(project_root, remote_project_root, sync_direction)
    print(f'sync_project command: {shlex.join(cmd)}')
    sync_log_path = os.path.join(user_home_local, 'tmp', 'sync.log')

    if not dry_run:
        with open(sync_log_path, 'a') as f:
            proc = subprocess.run(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode:
                err_msg = proc.stderr.decode(errors='replace')
                f.write(err_msg)
                raise RuntimeError(f'Error running project sync command: {shlex.join(cmd)}.  Error message:\n\t{err_msg}')
            else:
                f.write(proc.stdout.decode(errors='replace'))


print(remote_host)


if __name__ == '__main__':
    project_root = sys.argv[-1]
    for arg in sys.argv[1:]:
        if arg.startswith('--remote-host='):
            remote_host = arg.split('=')[1]
            break
    if remote_host == 'mac-clangd':
        sync_project(project_root, dry_run=False)
        # print(f'Will run command with local_path: {cwd}')

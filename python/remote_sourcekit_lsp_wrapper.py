from os import close

from threading import Thread, Lock
from rdt_utils import *
from lspobjects import Message, EMPTY_MESSAGE, INVALID_ID, get_body_start_idx

log_unmissable('AT BEGINNING OF REMOTE_SOURCEKIT_LSP_WRAPPER.PY')
user_home = '/Users/sam'
sklsp_path = '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/sourcekit-lsp'
set_xbs_envvars_arg = f'export SOURCEKIT_LOGGING=3 && export XBS_LOGPATH={user_home}/xbs.log'
remote_sourcekit_lsp_cmd = f'cd {shlex.quote(current_project_root_remote)} && {set_xbs_envvars_arg} && xcrun {sklsp_path}'
KB = 1024
MB = 1024 * 1024

# cmd = ['cd', '/Users/sam/Codingstuff/RemoteDevelopmentTools', '&&', 'xcrun', sklsp_path]
cmd = ['xcrun', sklsp_path]
# devnull = open(os.devnull, 'w')
sourcekit_lsp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=logfile_errors)

if (not sourcekit_lsp.stdin) or (not sourcekit_lsp.stdout):
    raise RuntimeError('Error opening pipe for sourcekit_lsp')

log_unmissable('SUCCESSFULLY LAUNCHED SOURCEKIT-LSP')

max_message_size = 20 * MB
# for arg in sys.argv[1:]:
#     if arg.startswith('--max-message-size='):
#         mms_str = arg.split('=')[1]
#         if mms_str.endswith('MB'):
#             max_message_size = int(mms_str[:-2]) * MB
#         elif mms_str.endswith('KB'):
#             max_message_size = int(mms_str[:-2]) * KB
#         else:
#             max_message_size = int(mms_str)


sourcekit_lsp_in_fd: int = sourcekit_lsp.stdin.fileno()
sourcekit_lsp_out_fd: int = sourcekit_lsp.stdout.fileno()
stdin_fd: int = int(sys.stdin.fileno())
stdout_fd: int = int(sys.stdout.fileno())
stdout_lock = Lock()
running = True

def remote_to_sourcekit():
    global running
    while running:
        data, body_start_idx = read_full_message(stdin_fd)
        msg = Message(data, body_start_idx=body_start_idx)
        if msg.method == 'shutdown':
            log_unmissable('RECEIEVED SHUTDOWN MESSAGE')
            running = False
            # break
        os.write(sourcekit_lsp_in_fd, data)
        log(b'Receieved from remote:\n\n' + data)

        # data = os.read(stdin_fd, 4096)
        # os.write(sourcekit_lsp_in_fd, data)
        # # os.write(
        # data, body_start_idx = read_full_message(stdin_fd)
        # os.read(stdin_fd, 5)
        # pass


def sourcekit_to_remote():
    global running
    if sourcekit_lsp is None:
        raise RuntimeError('Error, sourcekit_lsp failed to start')
    while running:
        data, body_start_idx = read_full_message(sourcekit_lsp_out_fd)
        msg = Message(data, body_start_idx=body_start_idx)
        if msg.method == 'shutdown':
            log_unmissable('RECEIEVED SHUTDOWN MESSAGE')
            running = False
            # break
        log(b'Receieved from sourcekit-lsp:\n\n' + data)
        if len(data) <= max_message_size:
            with stdout_lock:
                os.write(stdout_fd, data)
        else:
            # Do not pass on the message if it is too large
            continue



t1 = Thread(target=remote_to_sourcekit)
t2 = Thread(target=sourcekit_to_remote)

t1.start()
t2.start()

t1.join()
t2.join()

sourcekit_lsp.terminate()
# devnull.close()

#this is the new version

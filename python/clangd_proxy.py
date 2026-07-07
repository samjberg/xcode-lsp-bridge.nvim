import shlex
import os, sys, subprocess, threading
# from cached_message import CachedMessage, EMPTY_MESSAGE, INVALID_ID
from urllib.parse import unquote, urlparse
from rdt_utils import *
from retrieve_file import retrieve_header_file, headers_dir_path
from lspobjects import Message, EMPTY_MESSAGE, INVALID_ID, get_body_start_idx

log_unmissable('LSP_WRAPPER STARTED UP!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')


BUFFSIZE = 4096
CL_BSTR = b'Content-Length: '

log(f'sys.argv: {str(sys.argv)}\n')
log(f'clangd_args: {clangd_args}\n')
stdout_lock = threading.Lock()
# if not remote_host:
#     remote_host = config.get('remote_host', '')
if not user_home_remote:
    raise RuntimeError(f'Error, user home directory unknown for remote machine')
if not remote_host:
    raise RuntimeError(f'Error, remote host known')
cwd = os.getcwd()
cwdb = os.getcwdb()
remote_drive = 'Z'
remote_drive_prefix = f'{remote_drive}:\\'
remote_handled_file_extensions = ['.mm', '.swift']


nvim_data_path = 'C:/Users/sjber/AppData/Local/nvim-data'
# clangd_exe_path = 'C:/Users/sjber/AppData/Local/nvim-data/mason/bin/clangd.cmd'

clangd_exe_path = config_dct.get('clangd_exe', '')
if not clangd_exe_path:
    clangd_exe_path = find_clangd_exe()
    if clangd_exe_path:
        update_config(clangd_path=clangd_exe_path)
    else:
        raise RuntimeError('Error, unable to locate clangd.exe')

# clangd_exe_path = 'C:/Users/sjber/AppData/Local/nvim-data/mason/packages/clangd/clangd_22.1.6/bin/clangd.exe'
# clangd_exe_path = 'C:/Users/sjber/AppData/Local/nvim-data/mason/packages/clangd/clangd_22.1.0/bin/clangd.exe'
# clangd_exe_path = 'clangd'


log_unmissable(f'CLANGD_EXE_PATH: {clangd_exe_path}')


clangd = subprocess.Popen([clangd_exe_path, *clangd_args],
                          stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE,
                          stderr=logfile_errors)
remote_clangd = None
curr_clangd = clangd
using_remote_clangd = False

#Ensure clangd pipe was opened successfully
if (not clangd.stdin) or (not clangd.stdout):
    raise RuntimeError(f'Error opening pipe for clangd')

stdin_fd = sys.stdin.fileno()
stdout_fd = sys.stdout.fileno()
clangd_in_fd = clangd.stdin.fileno()
clangd_out_fd = clangd.stdout.fileno()
local_clangd_in_fd = clangd_in_fd
local_clangd_out_fd = clangd_out_fd
remote_clangd_in_fd = None

remote_clangd_out_fd = None

locally_handled_file_extensions = ['.cpp', '.c', '.hpp']

#cached message and index of body start for "initialization" message
has_initialized_successfully = False
cached_initialization_message: bytes = b''
cached_body_start_idx_initialization: int = 0

#cached message and index of body start for "initialized" message (the next message sent by client after initialization)
cached_initialized_message: bytes = b''
cached_body_start_idx_initialized: int = 0

cached_didopen_message: bytes = b''
cached_body_start_idx_didopen = 0

cached_messages = {'initialize'           : EMPTY_MESSAGE,
                   'initialized'          : EMPTY_MESSAGE,
                   'textDocument/didOpen' : EMPTY_MESSAGE}
cached_definition_requests: dict[int, Message] = {}




def is_initial_message(data: bytes):
    s = data.decode(errors='replace')
    if '"params":{' in s:
        pass



# Creates a LSP message from its body as a dict.  This is just a small convenience function
# to avoid having to type out Content-Length calculations over and over
def create_message_from_dict(dct: dict):
    body = json.dumps(dct)
    content_length = len(body)
    return f'Content-Length: {content_length}\r\n\r\n{body}'.encode()



def remote_clangd_is_running():
    return (remote_clangd is not None) and (remote_clangd_in_fd is not None) and (remote_clangd_out_fd is not None)


clangd_in_buff = b''
clangd_out_buff = b''
remote_clangd_in_buff = b''
remote_clangd_out_buff = b''

nvim_in_buff = b''
nvim_out_buff = b''


#test 


#Handles buffering issues and reads a full LSP message from file_descriptor fd
def read_full_message(fd: int) -> tuple[bytes, int]:
    data = b'' #buff
    while not CL_BSTR in data:
        data += os.read(fd, 1)
    while not data.endswith(b'\r\n\r\n'):
        data += os.read(fd, 1)

    content_length = parse_content_length_from_bytes(data)
    data += os.read(fd, content_length)
    body_start_idx = get_body_start_idx(data)

    # log(f'read {len(data)} bytes, and found a content-length of: {content_length}, for a total of {bytes_remaining} bytes remaining\n\n')
    while len(data) - body_start_idx < content_length:
        bytes_to_read = content_length - (len(data) - body_start_idx)
        data += os.read(fd, bytes_to_read)
    return data, body_start_idx


def translate_cached_message_for_remote(msg: bytes, body_start_idx: int) -> bytes:
    dct = json.loads(msg[body_start_idx:])
    params: dict = dct.get('params', {})
    if not params:
        log_raise_error('PARAMS NOT FOUND, IN TRANSLATE_INITIALIZATION_MESSAGE_FOR_REMOTE!!!!!')
    curr_root_uri = params.get('rootUri', '')
    curr_root_path = params.get('rootPath', '')
    if not curr_root_path:
        proxy_state = get_proxy_state()
        active_projects = sorted(proxy_state['active_projects'], key=lambda project: project['id'])
        log_unmissable('AT ACTIVE_PROJECTS!!!!')
        if len(active_projects) > 0:
            curr_root_path = active_projects[0]['rootPath']
            curr_root_uri = path_to_uri(curr_root_path)

    new_uri = clangd_path_mapping_uri(curr_root_uri)
    new_path = clangd_path_mapping_path(curr_root_path)
    params['rootUri'] = new_uri
    params['rootPath'] = new_path
    uri_len_diff = len(params['rootUri']) - len(curr_root_uri)
    path_len_diff = len(params['rootPath']) - len(curr_root_path)
    total_workspace_folders_len_diff = 0
    workspace_folders: list[dict] = params.get('workspaceFolders', [])
    if workspace_folders is None:
        workspace_folders = [{"uri": new_uri, "name": new_path}]
    else:
        for workspace_folder in workspace_folders:
            curr_wsf_name = workspace_folder.get('name', '')
            curr_wsf_uri = workspace_folder.get('uri', '')
            workspace_folder['name'] = clangd_path_mapping_path(curr_wsf_name)
            workspace_folder['uri'] = clangd_path_mapping_uri(curr_wsf_uri)
            name_len_diff = len(workspace_folder['name']) - len(curr_wsf_name)
            uri_len_diff = len(workspace_folder['uri']) - len(curr_wsf_uri)
            total_workspace_folders_len_diff += name_len_diff + uri_len_diff

    textdocument = params.get('textDocument', {})
    if textdocument:
        td_uri = textdocument['uri']
        if td_uri:
            textdocument['uri'] = clangd_path_mapping_uri(td_uri)
            params['textDocument'] = textdocument
    params['workspaceFolders'] = workspace_folders
    dct['params'] = params
    return create_message_from_dict(dct)

def translate_definition_request_for_remote(msg: bytes, body_start_idx: int) -> bytes:
    dct: dict = json.loads(msg[body_start_idx:])
    params: dict = dct.get('params', {})
    if not params:
        raise RuntimeError('ERROR, NO/EMPTY `params` KEY IN MSG BODY OF DEFINITION REQUEST')

    text_document: dict = params.get('textDocument', {})
    if not text_document:
        raise RuntimeError('ERROR, NO/EMPTY `textDocument` KEY IN PARAMS OF DEFINITION REQUEST')

    uri = text_document.get('uri', '')
    if not uri:
        raise RuntimeError('ERROR, NO/EMPTY `uri` IN TEXTDOCUMENT OF DEFINITION REQUEST')
    translated_uri = uri_windows_to_unix(uri)
    dct['params']['textDocument'] = translated_uri
    return create_message_from_dict(dct)


def initialize_remote_language_server(cached_messages: dict[str, Message]):
    global clangd, remote_clangd, remote_clangd_in_fd, remote_clangd_out_fd, clangd_in_fd, clangd_out_fd, using_remote_clangd
    if (remote_clangd is not None) and (remote_clangd_in_fd is not None) and (remote_clangd_out_fd is not None):
        return remote_clangd_in_fd, remote_clangd_out_fd
    for _ in range(100):
        log(b'GOT TO START OF INITIALIZE_REMOTE_LANGUAGE_SERVER!!!!!!!!!!!!!!!\n')

    proxy_state = get_proxy_state()
    active_projects: list[dict] = sorted(proxy_state.get('active_projects', []), key=lambda project: project['id'])
    # add_active_project({'pid': clangd.pid})

    ###################################### Handle opening remote clangd subprocess ###############################################
    # local_coding_root  = normalize_path(os.path.join(user_home_local, 'Coding'))
    # if local_coding_root.startswith('/'):
    #     local_coding_root = 'C:' + local_coding_root
    # remote_coding_root = normalize_path(os.path.join(user_home_remote, 'Codingstuff'))
    compile_commands_dir_local = os.path.join(current_project_root_local, 'build')
    compile_commands_dir_remote = clangd_path_mapping_path(compile_commands_dir_local)
    remote_clangd_cmd_args = ['xcrun', 'clangd', '--background-index',
                                f'--path-mappings={local_coding_root}={remote_coding_root}',
                                f'--compile-commands-dir={compile_commands_dir_remote}']
    remote_clangd_cmd = shlex.join(remote_clangd_cmd_args)

    remote_cmd = 'cd ' + shlex.quote(current_project_root_remote) + ' && ' + shlex.join(remote_clangd_cmd_args)

    full_remote_clangd_cmd = f"ssh -T {remote_host} 'cd {current_project_root_remote} && {remote_clangd_cmd}'"
    remote_cmd_args = ['ssh', '-T', remote_host, remote_cmd]
    remote_clangd = subprocess.Popen(remote_cmd_args,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=logfile)

    if (not remote_clangd.stdin) or (not remote_clangd.stdout):
        raise RuntimeError(f'Error opening pipe for clangd')
    remote_clangd_in_fd = remote_clangd.stdin.fileno()
    remote_clangd_out_fd = remote_clangd.stdout.fileno()
    ################################################################################################################################



    ############################ Replay initialize message to remote clangd after translating it ###################################
    #send cached initialization message to remote clangd AFTER handling path conversion and whatnot
    log_unmissable(b'BEFORE LOADING initialize FROM CACHED_MESSAGES!!!!!')
    init_msg = cached_messages['initialize']
    # dct: dict = json.loads(init_msg.message[init_msg.body_start_idx:])
    dct: dict = init_msg.dct
    params = dct.get('params', {})
    if params:
        # Also add the current project to the list of active projects for a similar reason
        project_root = params.get('rootPath', '')
        if project_root:
            project: dict = {'rootPath': project_root, 'id': get_available_id(proxy_state, 'active_projects')}
            if not project_is_active(project_root):
                add_active_project(project, proxy_state)
        else:
            if len(active_projects) > 0:
                project_root = active_projects[0]['rootPath']
                params['rootPath'] = project_root
                params['rootUri'] = path_to_uri(project_root)

        dct['params'] = params
        new_msg = create_message_from_dict(dct)
        body_start_idx = new_msg.find(b'\r\n\r\n') + 4
        init_msg = Message(new_msg, body_start_idx)

    translated_init_msg = translate_cached_message_for_remote(init_msg.as_bytes(), init_msg.body_start_idx)
    log(translated_init_msg)
    log_unmissable(b'AFTER INIT_MSG!!!!!!!!')
    os.write(remote_clangd_in_fd, translated_init_msg)
    initialization_resp, body_start_idx = read_full_message(remote_clangd_out_fd)
    ################################################################################################################################




    ############################ Replay initialized message to remote clangd after translating it ###################################
    initialized_msg_body = b'{"method":"initialized","params":{},"jsonrpc":"2.0"}'
    content_length = len(initialized_msg_body)
    initialized_msg = f'Content-Length: {content_length}\r\n\r\n'.encode(errors='replace') + initialized_msg_body

    body_start_idx = initialized_msg.find(initialized_msg_body)
    if not initialized_msg:
        err_msg = 'MISSING CACHED INITIALIZED (NOTE THE \'D\') MESSAGE!!!!!'
        log_unmissable(err_msg)
        raise RuntimeError(err_msg)
    # translated_initialized_msg = translate_cached_message_for_remote(initialized_msg, body_start_idx, current_project_root_local)
    log('\n\n\nTRANSLATED INITIALIZED (NOTE THE D) MESSAGE:')
    log(initialized_msg)
    os.write(remote_clangd_in_fd, initialized_msg)
    ################################################################################################################################

    ######################################### Start the remote clangd reader thread ################################################
    remote_reader_thread = threading.Thread(target=remote_clangd_to_nvim, args=[remote_clangd_out_fd])
    remote_reader_thread.start()
    using_remote_clangd = True
    ################################################################################################################################

    log_unmissable(b'GOT TO END OF INITIALIZE_REMOTE_LANGUAGE_SERVER!!!!!!!!!!!!!!!')
    return remote_clangd_in_fd, remote_clangd_out_fd


def classify_did_open_uri(uri: str, languageId: str) -> URIType:
    path = uri_to_path(uri).strip()
    if not path_has_drive_letter(path) or languageId in ['objc', 'objcpp', 'swift']:
        if path.endswith('.h'):
            return URIType.REMOTE_HEADER
        else:
            return URIType.REMOTE_PROJECT

    normed_path = normalize_path(path, strip_drive=True)
    headers_dir_path_normed = normalize_path(headers_dir_path, strip_drive=True)
    if normed_path.startswith(headers_dir_path_normed):
        return URIType.REMOTE_HEADER

    return URIType.LOCAL_PROJECT

def handle_textdocument_did_open(msg: bytes, msg_dct={}):
    global clangd_in_fd, clangd_out_fd, remote_clangd_in_fd, remote_clangd_out_fd

    log_unmissable('GOT TO START OF HANDLE_TEXTDOCUMENT_DID_OPEN!!!!!!!!!!!!!!!!')
    dct = msg_dct if msg_dct else json.loads(msg)
    method = dct.get('method', '')
    if method != 'textDocument/didOpen':
        log_raise_error('ERROR ERROR ERROR, METHOD IS NOT textDocument/didOpen IN HANDLE_TEXTDOCUMENT_DID_OPEN!!!!!!')
    params: dict = dct.get('params', {})
    if not params:
        log_raise_error("ERROR ERROR ERROR, 'params' NOT FOUND IN DCT IN HANDLE_TEXTDOCUMENT_DID_OPEN")

    text_document: dict = params.get('textDocument', {})
    if not text_document:
        log_raise_error("ERROR ERROR ERROR: 'textDocument' NOT FOUND IN 'params' OF 'textDocument/didOpen' MESSAGE!!!!!!!!")
    uri = text_document.get('uri', '')
    path = uri_to_path(uri)
    if not path:
        raise RuntimeError(f'Error getting uri and converting to path.  uri: {uri}\npath: {path}\n')

    languageId = text_document.get('languageId', '')
    uri_type = classify_did_open_uri(uri, languageId)
    match uri_type:
        case URIType.LOCAL_PROJECT:
            log_unmissable('URI TYPE: LOCAL PROJECT')
        case URIType.REMOTE_PROJECT:
            log_unmissable('URI TYPE: REMOTE PROJECT')
        case URIType.REMOTE_HEADER:
            log_unmissable('URI TYPE: REMOTE HEADER')


    if not languageId:
        log_raise_error("ERROR ERROR ERROR: 'languageId' NOT FOUND IN 'textDocument' OF 'params' OF MESSAGE!!!!!!!!!!!!")

    log(f'\n\n\nLANGUAGE_ID: {languageId}\n')
    log(f'dct: {dct}\n')


    # The normal case, where the file is inside the project root
    # if is_subdir(path, current_project_root_local):
    if is_subdir(path, current_project_root_local):
        # if the file is an "apple" language, check if remote clangd is started, if not start it.
        # in either case, set clangd_in_fd and clangd_out_fd
        if languageId in ['objc', 'objcpp', 'swift']:
            # If the remote language server has not yet been initialized and the filetype neccesitates the remote language server
            # if (remote_clangd_in_fd is None) or (remote_clangd_out_fd is None):
            if not remote_clangd_is_running():
                if not cached_initialization_message:
                    log_raise_error('ERROR ERROR: Attempted to start remote language server, but the cached initialization message is empty')
                remote_clangd_in_fd, remote_clangd_out_fd = initialize_remote_language_server(cached_messages)

            text_document['uri'] = clangd_path_mapping_uri(uri)
            new_msg = create_message_from_dict(dct)
            if remote_clangd_in_fd is None:
                raise RuntimeError('ERROR, remote_clangd_in_fd IS NONE AT END OF HANDLE_TEXTDOCUMENT_DIDOPEN')
            log('WRITING TO REMOTE CLANGD IN HANDLE_TEXTDOCUMENT_DID_OPEN:\n' + new_msg.decode())
            os.write(remote_clangd_in_fd, new_msg)
        else:
            log('WRITING TO LOCAL CLANGD IN HANDLE_TEXTDOCUMENT_DID_OPEN:\n' + msg.decode())
            os.write(clangd_in_fd, msg)
    # Case where the opened file is OUTSIDE of the project root, usually this will be remote header files
    else:
        if languageId in ['objc', 'objcpp', 'swift']:
            if not remote_clangd_is_running():
                remote_clangd_in_fd, remote_clangd_out_fd = initialize_remote_language_server(cached_messages)
            text_document['uri'] = clangd_path_mapping_uri(uri)
            new_msg = create_message_from_dict(dct)
            if remote_clangd_in_fd is None:
                raise RuntimeError('ERROR, remote_clangd_in_fd IS NONE AT END OF HANDLE_TEXTDOCUMENT_DIDOPEN')
            log('WRITING TO REMOTE CLANGD IN ELSE BRANCH OF HANDLE_TEXTDOCUMENT_DID_OPEN:\n' + new_msg.decode())
            os.write(remote_clangd_in_fd, new_msg)
        else:
            os.write(clangd_in_fd, msg)





# This function can only get called for remote files
def handle_textdocument_definition(msg: Message):
    data = msg.data
    body_start_idx = msg.body_start_idx
    dct = msg.dct
    if dct.get('id', INVALID_ID) != msg.id:
        log_raise_error('ERROR, handle_textdocument_definition RECEIVED A CACHED_MESSAGE WHOSE ID DOES NOT MATCH ITS ACTUAL ID')
    result = dct.get('result', [])
    if not result:
        raise RuntimeError('Error, textDocument/definition RESPONSE HAS NO `result` ENTRY!!!!')
    result = result[0]
    uri = result.get('uri', '')
    log_unmissable(f'Got URI from remote_clangd definition response: {uri}')
    if not uri:
        log_raise_error('ERROR, textDocument/definition RESPONSE CONTAINED AN EMPTY URI STRING!!!')

    uri_is_windows = is_windows_uri(uri)

    if not uri_is_windows:
        remote_path = uri[7:]
        safe_remote_path = unquote(urlparse(remote_path).path)
        local_path = retrieve_header_file(safe_remote_path)
        local_path_normed = normalize_path(local_path, strip_drive=True)
        headers_dir_path_normed = normalize_path(headers_dir_path, strip_drive=True)
        if not os.path.exists(local_path_normed):
            if not local_path_normed.startswith(headers_dir_path_normed):
                if local_path_normed.startswith('/'):
                    local_path_normed = os.path.join(headers_dir_path_normed, local_path_normed[1:])
                else:
                    local_path_normed = os.path.join(headers_dir_path, local_path_normed)
                local_path_normed = normalize_path(local_path_normed)

            # This attempt at handling the request failed and the file is not found at the expected local location.
            # Currently
            if not os.path.exists(local_path_normed):
                #try sending to local clangd.  cached_msg hasnt been modified yet, so we can just send it as is
                raise RuntimeError(f'Error, file retreival failed silently. File not found at expected location: {local_path_normed}')
        local_path = ensure_drive_letter(local_path)
        local_uri = path_to_uri(local_path_normed)
        result['uri'] = local_uri
        dct['result'] = [result]
    else:
        #it is a windows uri, meaning it is a local file.  Here we only perform unquoting/escaping and do nothing else
        path = uri_to_path(uri)
        safe_path = ensure_drive_letter(unquote(urlparse(path).path))
        safe_path_normed = normalize_path(safe_path, '\\')
        uri = path_to_uri(safe_path_normed)
        result['uri'] = uri
        dct['result'] = [result]
        log_unmissable(f'IN HANDLE_TEXTDOCUMENT_DEFINITION, uri IS A WINDOW URI.  URI: {uri}')

    new_msg_bytes = create_message_from_dict(dct)
    with stdout_lock:
        os.write(stdout_fd, new_msg_bytes)
    log(b'\nSENT TO NEOVIM:\n\n' + new_msg_bytes)





def set_cached_message(message: Message, id: int = -1):
    global cached_initialization_message, cached_initialized_message, cached_body_start_idx_initialization, cached_body_start_idx_initialized, cached_messages
    method = message.method
    data = message.data
    body_start_idx = message.body_start_idx
    if id == -1:
        msg_id = message.get('id', default_value=-1)
        if isinstance(msg_id, int):
            id = msg_id
    match method:
        case 'initialize':
            cached_initialization_message = data
            cached_body_start_idx_initialization = body_start_idx
            cached_messages['initialize'] = message
            # cached_messages['initialize'] = CachedMessage(cached_initialization_message, cached_body_start_idx_initialization, id)
        case 'initialized':
            cached_initialized_message = data
            cached_body_start_idx_initialized = body_start_idx
            cached_messages['initialized'] = Message(cached_initialized_message, id, cached_body_start_idx_initialized)
        case 'textDocument/didOpen':
            cached_didopen_message = data
            cached_body_start_idx_didopen = body_start_idx
            cached_messages['textDocument/didOpen'] = Message(cached_didopen_message, id, cached_body_start_idx_didopen)
        case _:
            log_unmissable('UNKNOWN MESSAGE TYPE IN SET_CACHED_MESSAGE!!!!!!!')

def set_cached_definition_request(id: int, data: bytes, body_start_idx: int):
    global cached_definition_requests
    cached_definition_requests[id] = Message(data, id, body_start_idx)

def nvim_to_backend():
    while True:
        data, body_start_idx = read_full_message(stdin_fd)
        try:
            msg = Message(data, body_start_idx=body_start_idx)
            method = msg.method
            dct = msg.dct
            # dct: dict = json.loads(data[body_start_idx:])
            if type(dct) == dict:
                if len(dct) > 0:
                    log('\n\n\n\n\nDecoded dict keys:\n')
                    for key in dct.keys():
                        log(f'\t{str(key)}\n')
                    log('\n\n\n')

            params = msg.get('params', default_value={})
            if method == 'shutdown':
                log('METHOD IS SHUTDOWN')
                clear_proxy_state()
                fd = remote_clangd_in_fd if using_remote_clangd else clangd_in_fd
                if fd is None:
                    raise RuntimeError('fd is None in shutdown branch')
                os.write(fd, data)
                break
                # os.write(std


            id = msg.get('id', default_value=-5)

            if params:
                # if method is 'initialize', store the full message for later use when initializing remote language server
                if method == 'initialize':
                    if not cached_messages['initialize']:
                        global current_project_root_local
                        new_project_root = params.get('rootPath', '')
                        if new_project_root:
                            current_project_root_local = new_project_root
                        # Only run the initialize routine if remote_clangd has not already started
                        if remote_clangd is None:
                            set_cached_message(msg)
                            # set_cached_message('initialize', data, body_start_idx)

                # if method is 'initialized' (note the 'd'), cache the initialized message
                elif method == 'initialized':
                    if not cached_messages['initialized']:
                        set_cached_message(msg)

                # handle document being opened
                elif method == 'textDocument/didOpen':
                    if not cached_messages['textDocument/didOpen']:
                        set_cached_message(msg)
                        handle_textdocument_did_open(data, dct)
                        #use continue to ensure we don't double write the textDocument/didOpen to remote clangd
                        #(that message is sent inside of handle_textdocument_did_open, along with the initialize and initialized playbacks)
                        continue

                # # handle go to definition request so that we can handle the remote file case (objc/objcpp/swift system/api header files...)
                elif method == 'textDocument/definition' or (id in cached_definition_requests):
                    if using_remote_clangd:
                        # id = dct.get('id', INVALID_ID)
                        log_unmissable(f'SETTING CACHED ID FOR DEFINITION REQUEST, ID: {id}')
                        if id:
                            set_cached_definition_request(id, data, body_start_idx)


        except json.JSONDecodeError as e:
            log(b'FAILED TO DECODE JSON.  DATA:\n\n\n' + data + b'\n\n\n')
            log_raise_error(f'FAILED TO DECODE JSON.  Error msg: {e}')


        log(b'\n\nRECEIVED from NEOVIM:\n' + data + b'\n\n')
        if (not data) or (clangd.stdin is None):
            break

        # Write data from nvim to local or remote clangd, depending on the current mode
        if not using_remote_clangd:
            os.write(clangd_in_fd, data)
            log(b'\n\nSENT to CLANGD:\n' + data + b'\n\n')
            clangd.stdin.flush()
        else:
            # log_unmissable('USING REMOTE CLANGD!!!!!!!!')
            if remote_clangd_in_fd is None:
                raise RuntimeError(f'ERROR, TRIED TO WRITE TO REMOTE CLANGD IN FD, BUT IT IS NONE')
            if remote_clangd is None:
                raise RuntimeError(f'ERROR, TRIED TO WRITE TO REMOTE CLANGD IN FD, BUT REMOTE_CLANGD IS NONE')
            if remote_clangd.stdin is None:
                raise RuntimeError(f'ERROR, TRIED TO WRITE TO REMOTE CLANGD IN FD, BUT REMOTE_CLANGD_STDIN IS NONE')
            log(b'\n\nSENT to REMOTE_CLANGD:\n' + data + b'\n\n')
            os.write(remote_clangd_in_fd, data)
            remote_clangd.stdin.flush()


def local_clangd_to_nvim():
    while True:
        if clangd.stdout is None:
            break
        data, body_start_idx = read_full_message(clangd_out_fd)
        log(b'\n\nRECEIVED from CLANGD:\n' + data + b'\n\n')
        if not data:
            break
        with stdout_lock:
            os.write(stdout_fd, data)
        log(b'\n\nSENT to NEOVIM:\n' + data + b'\n\n')
        sys.stdout.buffer.flush()


def remote_clangd_to_nvim(fd: int):
    log_unmissable('REMOTE CLANGD WAS LAUNCHED!!!!!!!!!!!!')
    while True:
        if clangd.stdout is None:
            break
        data, body_start_idx = read_full_message(fd)
        log(b'\n\nRECEIVED from REMOTE CLANGD:\n' + data + b'\n\n')
        if not data:
            break

        dct: dict = json.loads(data[body_start_idx:])
        id = dct.get('id', INVALID_ID)
        #if id is in cached_definition_requests, that means that this is the response to a definition request
        # I THINK THIS MIGHT BE THE PROBLEM.  WE ARE EXECUTING HANDLE_TEXTDOCUMENT_DEFINITION ANY TIME THE ID IS CACHED
        # So I think that it is being called even for local files when Go To Definition is used.  We need to fix that somehow,
        # probably by preventing the cacheing from happening in the first place (in nvim_to_backend)
        if id in cached_definition_requests:
            handle_textdocument_definition(Message(data, id, body_start_idx))
            del cached_definition_requests[id]
            continue #continue to avoid writing non-translated definition path message to nvim




        with stdout_lock:
            os.write(stdout_fd, data)
        log(b'\n\nSENT to NEOVIM:\n' + data + b'\n\n')
        sys.stdout.buffer.flush()



if not clangd.stdin or not clangd.stdout:
    raise RuntimeError('Pipe not initialized successfully')


t1 = threading.Thread(target=nvim_to_backend)
t2 = threading.Thread(target=local_clangd_to_nvim)



t1.start()
t2.start()

t1.join()
t2.join()

clangd.terminate()

if not logfile.closed:
    logfile.close()
if not logfile_errors.closed:
    logfile_errors.close()
clear_proxy_state()



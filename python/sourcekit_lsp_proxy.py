from json import decoder
import shlex
import os, sys, subprocess, threading
# from cached_message import CachedMessage, EMPTY_MESSAGE, INVALID_ID
from urllib.parse import unquote, urlparse
from rdt_utils import *
from retrieve_file import retrieve_header_file, headers_dir_path
from lspobjects import Message, EMPTY_MESSAGE, INVALID_ID, get_body_start_idx
from definition_mapping import *
from track_buffers import *

sourcekit_in_lock = threading.Lock()
stdout_lock = threading.Lock()
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
# remote_sourcekit_lsp_cmd = f'cd {shlex.quote(current_project_root_remote)} && xcrun sourcekit-lsp'
sklsp_path = '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/sourcekit-lsp'
pypath = '/Library/Frameworks/Python.framework/Versions/3.14/bin/python3'
set_xbs_envvars_arg = f'export SOURCEKIT_LOGGING=3 && export XBS_LOGPATH={user_home_remote}/xbs.log'
remote_sourcekit_lsp_cmd = f'cd {shlex.quote(current_project_root_remote)} && {set_xbs_envvars_arg} && xcrun {sklsp_path}'
# remote_sourcekit_lsp_cmd = f'cd {shlex.quote(current_project_root_remote)} && {set_xbs_envvars_arg} && {pypath} {sklsp_wrapper_path}'
# remote_sourcekit_lsp_cmd = 'cd ' + shlex.quote(current_project_root_remote) + ' && xcrun ' + sklsp_path + ' 2>/Users/sam/tmp/sklsp.log'
remote_cmd_args = ['ssh', '-T', remote_host, *shlex.split(remote_sourcekit_lsp_cmd)]
dev_null = open(os.devnull, 'w')
stderr = dev_null
# stderr = open('C:/Users/sjber/tmp/lsp_proxy_error_log.txt', 'ab')
sourcekit_lsp = subprocess.Popen(remote_cmd_args,
                    stdin = subprocess.PIPE,
                    stdout = subprocess.PIPE,
                    stderr=stderr)

stdin_fd = sys.stdin.fileno()
stdout_fd = sys.stdout.fileno()

if (not sourcekit_lsp.stdin) or (not sourcekit_lsp.stdout):
    raise RuntimeError('Error opening pipe for remote sourcekit_lsp')

sourcekit_lsp_in_fd = sourcekit_lsp.stdin.fileno()
sourcekit_lsp_out_fd = sourcekit_lsp.stdout.fileno()

# remote_sourcekit_lsp_args = ['sourcekit-lsp', 

definition_cache: dict[str, dict] = load_definition_cache()
shutting_down = False




def cache_message(msg: Message) -> None:
    '''
    Stores a Message object `msg` in `cached_messages` by its id
    A `RuntimeError` is raised if there is already another cached message with the same id.
    '''
    id = msg.id
    if not id or (id == -1):
        raise RuntimeError(f'Error caching message, invalid id: {id}')
    if id in cached_messages:
        raise RuntimeError(f'Error, attempted to cache message: {msg}, but there is already a cached message with the same id: {cached_messages[id]}')
    cached_messages[id] = msg
    # currently_used_ids.add(id)



def process_result(res: dict) -> dict:
    '''
    Processes a result.  This is really just purely a helper function for handle_textdocument_definition
    It doesnt really conceptually make that much sense as a function, but it is useful just because
    we need to do this process either to a single dict OR to a list of dicts.  So this code would have to be
    repeated multiple times in handle_textdocument_definition if it wasn't a function.  So...

    In terms of what this function actually does, it takes an INDIVIDUAL result of a textDocument/definition response
    The "result" can be a list[dict] or just a dict.  This function must take specifically an individual dict
    It processes that dict by checking if the "uri" is NOT a project path (not recursively in the project root).
    If it is not, then it attempts to retrieve the file from remote, or do nothing if already cached.  And then finally
    it changes the "uri" value to the local path of the file.
    '''
    uri: str = res.get('uri', '')
    path = uri_to_path(uri)
    if not is_project_path(path):
        log_unmissable(f'NOT A PROJECT PATH: {path}')
        normed_path = normalize_path(path, strip_drive=True)
        new_path = retrieve_header_file(normed_path)
        res['uri'] = path_to_uri(new_path)
        return res

    if is_project_path(path):
        if is_windows_uri(uri) and not is_subdir(path, headers_dir_path):
            return res
    return translate_paths_recursively_for_remote(res, REMOTE_TO_LOCAL)


def handle_textdocument_definition_response(msg: Message):
    '''
    Handles the RESPONSE to a textDocument/definition request.  It does all necessary work,
    both processing the message (path translation etc) as well as sending the response.
    '''
    log_unmissable(f'IN HANDLE_TEXTDOCUMENT_DEFINITIION_RESPONSE.  CURRENT PROJECT ROOT: {current_project_root_local}')
    results: list[dict] = msg.dct.get('result', [])
    if not results:
        raise RuntimeError('Error, empty result list in textDocument/definition response')

    if isinstance(results, list):
        result = results[0]
    elif isinstance(results, dict):
        result = results

    result = results[0]
    uri: str = result.get('uri', '')
    if not uri:
        log_raise_error('ERROR, textDocument/definition RESPONSE CONTAINED AN EMPTY URI STRING')

    translated_dct = msg.translate_paths(REMOTE_TO_LOCAL, inplace=False)
    translated_msg = Message(translated_dct)


    if isinstance(results, list):
        log('Processing results list\n\n\n')
        new_results = []
        for i, res in enumerate(results):
            log(f'Result before: {res}\n\n\n\n')
            # results[i] = process_result(res)
            new_results.append(process_result(res))
            log(f'Result after: {new_results[-1]}\n\n\n\n')
        translated_msg.dct['result'] = new_results
    elif isinstance(results, dict):
        translated_msg.dct['result'] = process_result(results)
    else:
        raise TypeError(f'Error, textDocument/definition response "result" is neither a list nor dict: {type(results)}')

    # Analyze translated_msg to determine if the definition result location is in a generated swift interface file
    translated_uri = translated_msg.get('uri', recursive=True)
    translated_path = uri_to_path(translated_uri)
    log_unmissable(f'tranlsated_uri: {translated_uri}')
    if is_subdir(translated_path, headers_dir_path):
        log_unmissable(f'CACHING DEFINITION REQUEST.  TRANSLATED_PATH: {translated_path}')
        # translated_path is a subdirectory of headers_dir_path, meaning that it is a generated swift interface file,
        # or at the very least some sort of header file that isn't directly part of the project.  In either case,
        # run the caching logic
        req = DefinitionRequest(cached_messages[translated_msg.id])
        resp = DefinitionResponse(translated_msg)
        for res in resp.results:
            path = normalize_path(uri_to_path(res.uri), strip_drive=True)
            if path.startswith('/var/folders/'):
                res.tranlsate_uri_for_remote_headers()

        if not req.uri in open_buffers:
            raise RuntimeError(f"Error, '{req.uri}' not found in open_buffers while trying to add a symbol: '{req.symbol}' from it to definition_cache")

        add_definition_to_cache(definition_cache, req, resp)

    with stdout_lock:
        os.write(stdout_fd, translated_msg.as_bytes())




def handle_textdocument_did_open(msg: Message):
    log(f'IN HANDLE_TEXTDOCUMENT_DID_OPEN.  type(msg): {type(msg)}')
    method = msg.method
    if method != 'textDocument/didOpen':
        log_raise_error('ERROR ERROR ERROR, METHOD IS NOT textDocument/didOpen in HANDLE_TEXTDOCUMENT_DID_OPEN!!!!!!!')
    params: dict = msg.dct.get('params', {})
    if not params:
        log_raise_error("ERROR ERROR ERROR, 'params' NOT FOUND IN DCT IN HANDLE_TEXTDOCUMENT_DID_OPEN")

    text_document: dict = params.get('textDocument', {})
    if not text_document:
        log_raise_error("ERROR ERROR ERROR: 'textDocument' NOT FOUND IN 'params' OF 'textDocument/didOpen' MESSAGE!!!!!!!!")


    text = text_document.get('text', '')
    if not text:
        raise RuntimeError('Error, text not found or is empty in handle_textdocument_did_open')


    # translate the msg and send the translated message to sourcekit-lsp
    translated_dct = msg.translate_paths(inplace=False)
    translated_msg = Message(translated_dct, id=msg.id)
    translated_data = translated_msg.as_bytes()

    # log('These are the exact bytes being written to sourcekit-lsp for didOpen:\n')
    log(f'SENDING TO REMOTE SOURCEKIT-LSP:\n')
    log(translated_data)
    log('\n\n')

    # log(translated_data)
    # log('\n\n')
    with sourcekit_in_lock:
        os.write(sourcekit_lsp_in_fd, translated_data)

    # Create Buffer object for newly opened buffer specified in msg and add it to the open_buffers dict
    buf = Buffer(msg)
    log_unmissable(f'Adding buffer: {buf.uri} to open_buffers')

    # Create textDocument/documentSymbol request message and send it to sourcekit-lsp
    # The response to this will be handled by backend_to_nvim, which will update buf.documentSymbols
    uri = buf.uri
    path_normed = normalize_path(buf.path, strip_drive=True)
    headers_dir_path_normed = normalize_path(headers_dir_path, strip_drive=True)
    log(f'headers_dir_path_normed: {headers_dir_path_normed}')
    log(f'path_normed: {path_normed}')
    # if not path_normed.startswith(headers_dir_path_normed):
    if not is_subdir(buf.path, headers_dir_path_normed):
        if not buf.ds_update_in_flight:
            documentsymbol_req = create_documentsymbol_request(uri)
            req_bytes = documentsymbol_req.as_bytes()
            cache_message(documentsymbol_req)
            log(f'SENDING (documentSymbol request) TO REMOTE SOURCEKIT-LSP:\n')
            log(req_bytes)
            log('\n\n')
            with sourcekit_in_lock:
                os.write(sourcekit_lsp_in_fd, req_bytes)
            buf.ds_update_in_flight = True

    else:
        log('IT IS A INTERFACE FILE.  NOT SENDING DOCUMENTSYMBOL REQUEST')

    uri = text_document.get('uri', '')
    if not uri:
        log_raise_error('ERROR GETTING URI IN HANDLE_TEXTDOCUMENT_DID_OPEN')
    path = uri_to_path(uri)
    # Add buf to open_buffers
    open_buffers[buf.uri] = buf



def handle_textdocument_definition_request(msg: Message):
    '''
    Handles a textDocument/definition request, the actual message where the method is literally 'textDocument/definition'
    Because of how sourcekit-lsp works, it is necessary (if we don't want 10 seconds of lag loading swift interface files) to
    short circuit the definition process, and simple skip it altogether.   Never send a request to sourcekit-lsp at all,
    and instead just manually send a cached response to neovim.  This is what this function does.
    '''
    req = DefinitionRequest(msg)
    if not req.symbol:
        log('ERROR, DEFINITION REQUEST HAS NO SYMBOL.')
        if req.uri in open_buffers:
            buf = open_buffers[req.uri]
            log(f'Current state of buf:\n\n{buf.text}\n\n')
            symbol = get_symbol_at_buf(buf, req.line, req.character)
            log(f'FOUND SYMBOL: {symbol} IN BUFFER, ASSIGNING IT BACK TO req.symbol')
            req.symbol = symbol

    buf = open_buffers[req.uri]
    ds = buf.get_symbol_containing(req.position)
    if not ds:
        raise RuntimeError(f'Error, no DocumentSymbol found containing req.position: {req.position}')
    context = '/'.join(ds.get_full_context())
    dct = definition_cache_lookup_request(definition_cache, req, context)
    if not dct:
    # if not cache_key in definition_cache:
        # This definition request is NOT cached in definition_cache, so cache the message
        # in cached_messages (NOT in definition_cache).  Caching the definition to definition_cache will happen,
        # if it should happen at all, in handle_textdocument_definition_response, where the definition location is available

        # After caching the message, simply do path translation as usual and send the path-translated message to sourcekit-lsp
        log_unmissable(f'CACHING MESSAGE WITH id: {msg.id}')
        cache_message(msg)
        translated_dct = msg.translate_paths(inplace=False)
        translated_msg = Message(translated_dct)
        translated_data = translated_msg.as_bytes()
        with sourcekit_in_lock:
            os.write(sourcekit_lsp_in_fd, translated_data)

    else:
        # cache_key IS found in definition_cache.  Attempt to retrieve the DefinitionResponse object, raising an error if that fails
        # resp = definition_cache[cache_key].get('response', None)
        resp = dct.get('response', None)
        if not req.uri in open_buffers:
            raise RuntimeError(f'Error in handle_textdocument_definition_request: DefinitionRequest uri not found in open_buffers')
        buf = open_buffers[req.uri]
        ds = buf.get_symbol_containing(req.position)
        if not ds:
            raise RuntimeError('Error, a DocumentSymbol containing req.position was not found in buf')
        context = ds.get_full_context()
        log(f'CONTEXT CHAIN FOR DOCUMENTSYMBOL: {ds}\n')
        log(ds.context_str)


        if resp is None:
            raise RuntimeError(f'Error, response not found in definition_cache, even though the request cache_key exists there')
        elif not isinstance(resp, DefinitionResponse):
            raise TypeError(f'Error, response was found, but is not of type DefinitionResponse.  type: {type(resp)}')

        log_unmissable('MARKERMARKERMARKER')

        changed = False
        for res in resp.results:
            path = uri_to_path(res.uri)
            log(f'resuri before: {res.uri}\n')
            if not is_project_path(path):
                log_unmissable('NON PROJECT PATH FOUND IN WHATEVER')
                correct_path = os.path.join(headers_dir_path, normalize_path(path, strip_drive=True)[1:])
                res.uri = path_to_uri(correct_path)
                changed = True
            log(f'resuri after: {res.uri}\n')

        if changed:
            definition_cache[req.cache_key()]['response'] = resp
            save_definition_cache(definition_cache)

        log(f'resp_res_uri: {resp.results[0].uri}')
        log(f'resp as bytes: {resp.as_bytes()}')

        resp.id = msg.id
        resp.dct['id'] = msg.id




        # resp is a DefinitionResponse found in definition_cache, it is safe to use it to write a message back to nvim (stdout)
        # So we just write the contents of the cached DefinitionResponse as bytes to nvim (stdout)
        with stdout_lock:
            os.write(stdout_fd, resp.as_bytes())

def debounce_did_change_messages():
    '''This function handles debouncing textDocument/didChange messages.  Once a Buffer has been changed and then
       `debounce_interval` seconds pass, a textDocument/documentSymbol request is sent to sourcekit-lsp.  The point is to
       keep the `DocmentSymbol`s up to date for all buffers, without having to recompute them on literally every keypress'''
    debounce_interval = 0.5
    while not shutting_down:
        curr_time = time.monotonic()
        for uri, buf in open_buffers.items():
            if buf.needs_ds_update and ((curr_time - buf.last_change_time) >= debounce_interval):
                ds_req = create_documentsymbol_request(uri)
                cache_message(ds_req)
                req_bytes = ds_req.as_bytes()
                with sourcekit_in_lock:
                    os.write(sourcekit_lsp_in_fd, req_bytes)
                # buf's
                buf.needs_ds_update = False
                buf.ds_update_in_flight = True
        time.sleep(0.1)


def nvim_to_backend():
    '''
    Handles passing data from nvim to the sourcekit-lsp backend.
    '''
    while True:
        data, body_start_idx = read_full_message(stdin_fd)
        log(b'\n\nRECEIVED from NEOVIM:\n' + data + b'\n\n')
        msg = Message(data, body_start_idx=body_start_idx)
        method = msg.method

        # Add the id from currently_used_ids if msg has an id (not all do).  This is just a simple mechanism
        # for keeping track of currently used message ids, to help avoid id collisions when we have to completely
        # generate a message from scratch (including choosing an id, this helps to not choose an occupied id)
        if msg.id:
            currently_used_ids.add(msg.id)
        # uri = msg.get('uri', recursive=True, default_value='')


        # if method == 'initialize':
        #     cache_message(msg)

        # listen for definition request, and cache the message when it happens
        if method == 'textDocument/definition':
            # call handle_textdocument_definition_request, and then continue, so double writes to sourcekit-lsp dont happen
            # (all reading/writing, after the initial msg, is handles in handle_textdocument_definition_request)
            handle_textdocument_definition_request(msg)
            continue
            # log_unmissable(f'CACHING MESSAGE WITH id: {msg.id}')
            # cache_message(msg)
        elif method == 'textDocument/didOpen':
            handle_textdocument_did_open(msg)
            # handle_textdocument_did_open handles sending back the response, because it needs to also send a generated
            # textDocument/documentSymbol request, which should come after sourcekit-lsp receieves the textDocument/didOpen message
            # So this continue statement ensures that the os.write call at the end of this function doesnt get called, which would
            # cause the didOpen message to be sent twice
            continue

        elif method == 'textDocument/didClose':
            uri = msg.get('params', 'textDocument', 'uri')
            close_buffer(uri)

        elif method == 'textDocument/didChange':
            uri = msg.get('params', 'textDocument', 'uri')
            if not uri:
                raise RuntimeError(f'Error, no uri found in textDocument/didChange message: {str(msg)}')
            if not uri in open_buffers:
                raise RuntimeError(f'Error, buffer with uri: {uri} not found in open_buffers')
            buf: Buffer = open_buffers[uri]
            buf.apply_didchange_message(msg)


        translated_dct = msg.translate_paths(inplace=False)
        translated_msg = Message(translated_dct, id=msg.id)
        translated_data = translated_msg.as_bytes()
        log(b'\n\nSENDING TO REMOTE SOURCEKIT-LSP:\n' + translated_data + b'\n\n')

        if method == 'shutdown':
            global shutting_down
            shutting_down = True
            clear_proxy_state()
            log_unmissable('ABOUT TO CLOSE REMAINING BUFFERS')
            buf_uris = list(open_buffers.keys())
            for uri in buf_uris:
                log(f'CLOSING BUFFER FOR URI: {uri}')
                close_buffer(uri)

            with sourcekit_in_lock:
                os.write(sourcekit_lsp_in_fd, translated_data)
            break

        with sourcekit_in_lock:
            os.write(sourcekit_lsp_in_fd, translated_data)



def backend_to_nvim():
    '''
    Handles passing data from the sourcekit-lsp backend to nvim.
    '''
    while True:
        if sourcekit_lsp is None:
            break
        data, body_start_idx = read_full_message(sourcekit_lsp_out_fd)
        log(b'\n\nRECEIVED from REMOTE SOURCEKIT-LSP:\n' + data + b'\n\n')
        if not data:
            break
        msg = Message(data, body_start_idx=body_start_idx)
        # method = msg.method
        if msg.id in cached_messages:
            cached_msg: DefinitionRequest = cached_messages[msg.id]
            if cached_msg.method == 'textDocument/definition':
                handle_textdocument_definition_response(msg)
                del cached_messages[msg.id]
                log_unmissable('RECEIEVED TEXTDOCUMENT/DEFINITION MESSAGE RESPONSE')
                continue
            elif cached_msg.method == 'textDocument/documentSymbol':
                log_unmissable('RECEIEVED TEXTDOCUMENT/DOCUMENTSYMBOL MESSAGE RESPONSE')
                original_uri = cached_msg.get('params', 'textDocument', 'uri')
                uri = original_uri if is_windows_uri(original_uri) else clangd_path_mapping_uri(original_uri, REMOTE_TO_LOCAL)
                if not uri in open_buffers:
                    raise RuntimeError(f'Error, received documentSymbol response, but uri: {uri} for cached_msg was not found in open_buffers')
                buf = open_buffers[uri]
                new_document_symbols: list[DocumentSymbol] = document_symbols_from_message(msg, uri)

                # Only update buf.document_symbols and associated state if new_document_symbols is not an empty list, which
                # signifies that the textDocument/documentSymbol response was an error message, usually from a cancellation
                if new_document_symbols:
                    # Perform the actual documentSymbol update from the message
                    buf.document_symbols = new_document_symbols
                    # The documentSymbol update has been receieved, so set ds_update_in_flight to False
                    buf.ds_update_in_flight = False
                    # buf.document_symbols is now up to date, so set buf.needs_ds_update to False
                    buf.needs_ds_update = False
                    # remove cached_msg from cached_messages
                    del cached_messages[cached_msg.id]
                else:
                    # Receieved an error response to the documentSymbol request.  Try resending the request
                    req_bytes = cached_msg.as_bytes()
                    log(f'Receieved error response to textDocument/documentSymbol request.  Resending request:\n{req_bytes}')
                    with sourcekit_in_lock:
                        os.write(sourcekit_lsp_in_fd, req_bytes)

                # continue so that the message is not passed on to nvim.  Since it is a message created manually by the proxy,
                # nvim is not expecting a response and will produce an error if it receieves one
                continue
            # elif cached_msg.method == 'initialize':
                # msg is the response from the initialize request, cached_msg is the initialize request
                # Send a documentSymbol message for testing purposes
                # create_documentsymbol_request()


        translated_dct = msg.translate_paths(REMOTE_TO_LOCAL, inplace=False)
        translated_msg = Message(translated_dct, id=msg.id)
        translated_data = translated_msg.as_bytes()
        log(b'\n\nSENDING TO NEOVIM:\n' + translated_data + b'\n\n')
        with stdout_lock:
            os.write(stdout_fd, translated_data)

        # Remove the id from currently_used_ids if it is contained there.  This is just a simple mechanism
        # for keeping track of currently used message ids, to help avoid id collisions when we have to completely
        # generate a message from scratch (including choosing an id, this helps to not choose an occupied id)
        if msg.id in currently_used_ids:
            currently_used_ids.remove(msg.id)









# Launch the two main threads for nvim to backend and backend to nvim.  Backend here is the ssh connection to sourcekit-lsp
t1 = threading.Thread(target=nvim_to_backend)
t2 = threading.Thread(target=backend_to_nvim)
t3 = threading.Thread(target=debounce_did_change_messages)

# Start the threads
t1.start()
t2.start()
t3.start()


# Join the threads
t1.join()
t2.join()
t3.join()


# Perform some cleanup, ensure all log files are closed, clear the proxy state, etc
sourcekit_lsp.terminate()
if not logfile.closed:
    logfile.close()
if not logfile_errors.closed:
    logfile_errors.close()

dev_null.close()
clear_proxy_state()

log_unmissable('ABOUT TO CLOSE REMAINING BUFFERS')
for uri, buf in open_buffers.items():
    log(f'CLOSING BUFFER FOR URI: {uri}')
    close_buffer(uri)








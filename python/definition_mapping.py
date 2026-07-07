from rdt_utils import *
from lspobjects import Message, Position, Selection
from retrieve_file import headers_dir_path
from track_buffers import *


definition_cache_path = normalize_path(os.path.join(rdt_root_path, 'definition-cache.json'))

def get_symbol_at_buf(buf: Buffer, row: int, col: int, one_indexed=False) -> str:
    '''
    Gets the full token/symbol at (row, col) in the given Buffer `buf`
    If `one_indexed` is True, then 1 is subtracted from both row and col.  nvim passes rows (line) and cols (character) as 1-indexed,
    so `one_indexed` is True by default.
    '''
    if isinstance(buf, str):
        buf = open_buffers[buf]

    if one_indexed:
        row -= 1
        col -= 1

    # I genuinely didnt know you could do this until very recently, but you CAN enumerate directly over a file object.
    # And it is actually more memory efficient, because doing it this way (versus the equivalent thing with .readlines())
    # only loads 1 line at a time into memory, versus loading the whole file with .readlines()

    # with open(path, 'r') as f:
    # for i, line in enumerate(buf.lines):
    if row > len(buf.lines):
        raise RuntimeError(f'Error, line: {row} is greater than number of lines in buf')
    line = buf.lines[row]
    # if i == row:
    if len(line) < col:
        return ''
    start = col
    end = col
    while start >= 0 and not is_symbol_separator(line[start]):
        log(f'start: {start}\n')
        start -= 1
    while end < len(line) and not is_symbol_separator(line[end]):
        end += 1

    # add 1 to start because we went back until we found a space
    # we dont need to subtract 1 from end because of how slicing works, i.e. the ending space automatically won't be included
    start += 1
    return line[start:end]
    # return ''



def create_position(pos_dct: dict[str, int]):
    line = pos_dct.get('line', None)
    character = pos_dct.get('character', None)
    if (line is None) or (character is None):
        raise RuntimeError(f'Error creating Position object from position dict: {pos_dct}')
    return Position(line, character)



def create_selection(range_dct: dict[str, dict[str, int]]):
    start = create_position(range_dct.get('start', {}))
    end = create_position(range_dct.get('end', {}))
    return Selection(start, end)


class FileLocation:
    def __init__(self, uri: str, line: int, character: int):
        self.uri = uri
        self.path = uri_to_path(self.uri)
        self.line = line
        self.character = character

    def cache_key(self):
        return f'{self.uri}|line={self.line}|character={self.character}'

    def __str__(self):
        return self.cache_key()

    def __hash__(self):
        return hash(self.cache_key())



class DefinitionResult:
    '''Represents an individual result dict from a definition response.  This class does NOT represent
       the entire "result" list, just an individual object from that list
    '''
    def __init__(self, dct: dict):
        self.uri: str = dct.get('uri', '')
        range_dct: dict = dct.get('range', {})
        self.range: Selection = create_selection(range_dct)
        self.start: Position = self.range.start
        self.end: Position = self.range.end

    def tranlsate_uri_for_remote_headers(self):
        '''Translates the DefinitionResult's uri to be the same as it currently is, except for being rooted in
           `headers_dir_path` instead of the filesystem root.'''
        prev_uri = self.uri
        path = normalize_path(uri_to_path(self.uri), strip_drive=True)
        if is_subdir(path, headers_dir_path):
            return
        if path.startswith('/'):
            path = path[1:]
        translated_path = ensure_drive_letter(normalize_path(os.path.join(headers_dir_path, path)))
        self.uri = path_to_uri(translated_path)
        log(f'translated path from: {prev_uri} to {self.uri}')


    def as_dict(self):
        return {'uri': self.uri, 'range': {'start': self.start.as_dict(), 'end': self.end.as_dict()}}

    def __hash__(self):
        return hash(f'uri:{self.uri},range:{self.range}')



class DefinitionRequest(Message):
    '''
    Represents a definition request LSP message, providing easy access to various parameters in the JSON object without having
    to manually search through the dict to find them
    '''
    def __init__(self, req: Message|dict|bytes, symbol=''):
        # if isinstance(req, Message):
        #     self.msg: Message = req
        # elif isinstance(req, dict) or isinstance(req, bytes):
        #     self.msg: Message = Message(req)
        # else:
        #     raise TypeError(f'Error, invalid type for req: {type(req)}, must be Message|dict|bytes.  req: {req}')
        if isinstance(req, Message):
            self.data = req.data
        super().__init__(req)
        if self.method != 'textDocument/definition':
            raise RuntimeError(f'Error, invalid method for DefinitionRequest object: {self.method}')
        self.uri = self.get('params', 'textDocument', 'uri')
        self.line: int = self.get('params', 'position', 'line')
        self.character: int = self.get('params', 'position', 'character')
        self.position: Position = Position(self.line, self.character)
        self.file_location: FileLocation = FileLocation(self.uri, self.line, self.character)
        if self.uri in open_buffers:
            self.symbol: str = symbol if symbol else get_symbol_at_buf(self.uri, self.line, self.character, False)
        else:
            self.symbol: str = symbol if symbol else get_symbol_at_uri(self.uri, self.line, self.character, False)


    def cache_key(self, type: str = 'position'):
        if type == 'position':
            return self.file_location.cache_key()
        elif type == 'symbol':
            return f'{self.uri}|symbol={self.symbol}'
        raise ValueError("Error, cache_key `type` must be: 'position' or 'symbol'")
        # return self.file_location.cache_key()

    def __hash__(self):
        return hash(self.cache_key())



class DefinitionResponse(Message):
    '''
    Represents a definition response LSP message, providing easy access to various parameters in the JSON object without having
    to manually search through the dict to find them
    '''
    def __init__(self, resp: Message|dict|bytes):
        if isinstance(resp, Message):
            self.data = resp.data
        super().__init__(resp)
        result_lst = self.get('result')
        self.results = [DefinitionResult(res_dct) for res_dct in result_lst]

    def as_dict(self):
        return {'jsonrpc': '2.0', 'result': [res.as_dict() for res in self.results], 'id': self.id}

    def as_bytes(self):
        body = json.dumps(self.as_dict())
        content_length = len(body)
        return f'Content-Length: {content_length}\r\n\r\n{body}'.encode()

    def __hash__(self):
        return sum([hash(res) for res in self.results])

# Represents a value in a DefinitionCacheEntry
DefinitionCacheItem: TypeAlias = DefinitionRequest | DefinitionResponse | str
# Represents a single 'leaf' in the definition_cache, i.e. definition_cache[uri][symbol][i] is a DefinitionCacheEntry
DefinitionCacheEntry: TypeAlias = dict[str, DefinitionCacheItem]
# Represents the full definition cache itself.  It has the shape definition_cache[uri][symbol][index]
DefinitionCache: TypeAlias = dict[str, dict[str, list[DefinitionCacheEntry]]]


def load_definition_cache() -> DefinitionCache:
    with open(definition_cache_path, 'r') as f:
        dct: dict = json.load(f)
    def_cache: DefinitionCache = {}

    for uri, val in dct.items():
        def_cache[uri] = {}
        for symbol, reslst in val.items():
            lst: list[DefinitionCacheEntry] = []
            for subdct in reslst:
                req = DefinitionRequest(subdct.get('request', {}), symbol=symbol)
                resp = DefinitionResponse(subdct.get('response', {}))
                context = subdct.get('context', '')
                lst.append({'symbol': symbol, 'request': req, 'response': resp, 'context': context})
            def_cache[uri][symbol] = lst

    return def_cache


def save_definition_cache(definition_cache: DefinitionCache):
    log(f'current definition cache: {str(definition_cache)}')
    dct = {}
    for uri, val in definition_cache.items():
        dct[uri] = {}
        for symbol, reslst in val.items():
            lst = []

            #reslst is a list of dicts, where those dicts have the keys 'symbol', 'request', 'response', and 'context'
            for subdct in reslst:
                req: DefinitionCacheItem|None  = subdct.get('request', None)
                if not isinstance(req, DefinitionRequest):
                    raise RuntimeError('')
                resp: DefinitionCacheItem|None = subdct.get('response', None)
                if not isinstance(resp, DefinitionResponse):
                    raise RuntimeError('')
                context = subdct.get('context', None)
                if context is None:
                    raise RuntimeError(f"Error, key 'context' not found in subdct: {subdct}")
                if not req or not resp:
                    raise RuntimeError(f'Error, req or resp is None')
                lst.append({'symbol': symbol, 'request': req.dct, 'response': resp.as_dict(), 'context': context})
            dct[uri][symbol] = lst

    with open(definition_cache_path, 'w') as f:
        json.dump(dct, f)


def add_definition_to_cache(definition_cache: DefinitionCache, req: DefinitionRequest, resp: DefinitionResponse) -> None:
    '''
    Adds a definition request and response pair to the definition cache.
    `definition_cache`: The `dict` which represents the loaded definition cache.  Gotten by calling `load_definition_cache()`
    `req`: The `DefinitionRequest` that represents the request LSP message for the defintion.
    `resp`: The `DefinitionResponse` that represents the response message.
    `type`: Controls which type(s) of cache key is used.  Options are 'both', 'position', and 'symbol'
    '''

    symbol = req.symbol
    uri = req.uri
    buf = open_buffers.get(uri, None)
    if buf is None:
        raise RuntimeError(f'Error, failed to find open buffer for uri: {uri}')

    ds = buf.get_symbol_containing(req.position)
    context_str = ds.context_str if ds else ''

    if not uri in definition_cache:
        definition_cache[uri] = {symbol: []}
    elif not symbol in definition_cache[uri]:
        definition_cache[uri][symbol] = []

    # Add entry to definition_cache, and then save the definition_cache to disk
    definition_cache[uri][symbol].append({'symbol': symbol, 'request': req, 'response': resp, 'context': context_str})
    save_definition_cache(definition_cache)


def definition_cache_lookup_request(definition_cache: DefinitionCache, req: DefinitionRequest, context: str|None = None) -> DefinitionCacheEntry|None:
    uri = req.uri
    symbol = req.symbol
    uri_dct = definition_cache.get(uri, {})
    if not uri_dct:
        definition_cache[uri] = {}
        uri_dct = definition_cache[uri]
        # raise RuntimeError(f'Error, uri: {uri} not found in definition_cache')

    match_lst: list[dict] = uri_dct.get(symbol, [])
    # If lookup failed, or succeeded but is genuinely an empty list (which shouldn't be possible).
    # Either way, return an empty DefinitionCacheEntry
    if not match_lst:
        return {}


    # if context is None, meaning no value was passed, arbitrarily return the first result matching the uri and symbol
    # Note that None is used intentionally, because an empty context string represents a top level symbol 
    # (i.e. it has no context because it is a top level symbol)
    if not context:
        return match_lst[0]

    # context was passed, so run through all uri and symbol matches to find the best context match
    best_score = 0
    best_match_idx = 0
    context_parts = context.split('/')
    for idx, dct in enumerate(match_lst):
        ctx: str = dct.get('context', '')
        ctx_parts = ctx.split('/')
        score = 0
        for i in range(min(len(context_parts), len(ctx_parts))):
            if ctx_parts[i] == context_parts[i]:
                score += 1
            else:
                break
        if score > best_score:
            best_match_idx = idx
            best_score = score
    return match_lst[best_match_idx]





def create_documentsymbol_request(uri: str, translate_uri=True) -> Message:
    '''
    Creates a textDocument/documentSymbol request LSP message.  If `translate_uri` is True, `uri` is automatically converted
    to a remote uri (what is expected by sourcekit-lsp), whether it starts as a local or remote uri.  Otherwise it is used as is.
    '''
    id = get_available_documentsymbol_id()
    if translate_uri:
        if is_windows_uri(uri):
            uri = clangd_path_mapping_uri(uri, LOCAL_TO_REMOTE)
    dct = {'jsonrpc': '2.0', 'id': id, 'method': 'textDocument/documentSymbol', 'params': {'textDocument': {'uri': uri}}}
    return Message(dct)













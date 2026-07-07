from json import JSONDecodeError
from rdt_utils import *
from copy import deepcopy
from typing import Any

CL_BSTR = b'Content-Length: '
CL_STR = 'Content-Length: '
INVALID_ID = 0

@dataclass
class Position:
    line: int
    col: int
    def as_dict(self):
        return {'character': self.col, 'line': self.line}
    def __hash__(self):
        return hash(str(self))


@dataclass
class Selection:
    start: Position
    end: Position
    def as_dict(self):
        return {'start': self.start.as_dict(), 'end': self.end.as_dict()}
    def __hash__(self):
        return hash(f'start:{self.start},end:{self.end}')


def position_from_dict(dct: dict):
    if 'position' in dct:
        dct = dct['position']
    line: int = dct.get('line', -1)
    character: int = dct.get('character', -1)
    if (line == -1) or (character == -1):
        raise RuntimeError(f'Error creation position_from_dict, character and position not both found in dict: {dct}')
    return Position(line, character)

def selection_from_dict(dct: dict):
    if 'range' in dct:
        dct = dct['range']

    start = position_from_dict(dct.get('start', {}))
    end = position_from_dict(dct.get('end', {}))
    return Selection(start, end)



class Message:
    def __init__(self, data, id=0, body_start_idx=-1):
        self.dct = {}
        if isinstance(data, bytes):
            self.data = data
        elif isinstance(data, dict):
            self.dct = data
            body: str = json.dumps(self.dct)
            content_length = len(body)
            self.data = f'{CL_STR}{content_length}\r\n\r\n{body}'.encode()
        if not self.data:
            self.data: bytes = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.id = id
        if self.data:
            if not isinstance(self.data, bytes):
                raise RuntimeError('Error, self.data does not have type `bytes`')
            self.body_start_idx = body_start_idx if body_start_idx != -1 else get_body_start_idx(self.data)
            self.body = self.data[self.body_start_idx:]
            if not self.dct:
                self.dct: dict = json.loads(self.data[self.body_start_idx:])
            self.method = self.dct.get('method', '')
            if not self.id:
                self.id = self.dct.get('id', 0)
        else:
            self.body_start_idx = 0
            self.body = b''
            self.dct = {}
            self.method = ''

        if id in self.dct:
            self.id = self.dct['id']


    def get(self, *keys, default_value=None, recursive=False) -> Any:
        '''
        Returns a value from the JSON body of the message.
        `keys`: The JSON keys in order required to access the desired value i.e. msg.get('key1', 'key2', 'key3') 
            will return the same value as self.dct['key1']['key2']['key3'] if that JSON path exists
        `default_value`: The value to be returned if the supplied keys do not lead to an existing item in the dict
        `recursive`: If set to True, only the first argument of keys is used.  A breadth first search is performed to find the first entry of keys[0] in self.dct
        '''
        if recursive:
            return bfs_dict(self.dct, keys[0])

        # This just allows for keys to be passed as a single list of keys as well as by passing a sequence of keys as individual arguments
        if (len(keys) == 1) and (isinstance(keys[0], list) or isinstance(keys[0], tuple)):
            keys = keys[0]
        curr_dct: dict = self.dct
        for key in keys[:-1]:
            curr_dct = curr_dct[key]
        return curr_dct.get(keys[-1], None)


    def set(self, value, *keys):
        '''
        Sets a value in the JSON body of the message.
        `value`: The value to set at the location provided by `keys`
        `keys`: The JSON keys in order required to set the desired value i.e. msg.set('key1', 'key2', 'key3') 
            will behave the same as msg.dct['key1']['key2']['key3']=value if that JSON path exists
        `default_value`: The value to be returned if the supplied keys do not lead to an existing item in the dict
        '''

        # This just allows for keys to be passed as a single list of keys as well as by passing a sequence of keys as individual arguments
        if (len(keys) == 1) and (isinstance(keys[0], list) or isinstance(keys[0], tuple)):
            keys = keys[0]
        curr_dct: dict = self.dct
        for key in keys[:-1]:
            curr_dct = curr_dct[key]
        curr_dct[keys[-1]] = value

    def content_length(self) -> int:
        try:
            body_str = json.dumps(self.dct)
            return len(body_str)
        except JSONDecodeError as e:
            raise RuntimeError(f'Failed to decode dct JSON in Message.content_length().  Error message: {e}')

    def as_str(self):
        body: str = json.dumps(self.dct)
        content_length = len(body)
        return f'Content-Length: {content_length}\r\n\r\n{body}'

    def as_bytes(self):
        return self.as_str().encode()

    def translate_paths(self, direction=LOCAL_TO_REMOTE, inplace=True) -> dict:
        if not inplace:
            dct = deepcopy(self.dct)
            return translate_paths_recursively_for_remote(dct, direction)
        self.dct = translate_paths_recursively_for_remote(self.dct, direction)
        return self.dct

    def __eq__(self, other):
        if isinstance(other, Message):
            return self.as_bytes() == other.as_bytes()
        elif isinstance(other, bytes):
            return self.as_bytes() == other
        return False

    def __str__(self):
        return json.dumps(self.dct)

    def __repr__(self):
        return json.dumps(self.dct)

    def __bool__(self):
        return bool(self.dct)


EMPTY_MESSAGE = Message(b'')

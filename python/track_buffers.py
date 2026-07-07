from rdt_utils import *
from lspobjects import Message, Selection, Position, selection_from_dict, position_from_dict
import time

# Line Ending Types
LF = '\n'
CRLF = '\r\n'


def is_line_insertion(start: Position, end: Position, line: str) -> bool:
    if len(line) - start.col > 2:
        return False
    line_ending = line[start.col:]
    return line_ending == '\r\n' or line_ending == '\n'


class DocumentSymbol:
    def __init__(self, dct: dict, uri: str, parent = None):
        '''
        `dct`: A dict from a textDocument/documentSymbol response message.  It must be a dict for 1 individual documentSymbol, not the full list of documentSymbols.
        `uri`: The uri this `DocumentSymbol` is associated with
        '''
        self.symbol: str = dct.get('name', '')
        if not self.symbol:
            raise RuntimeError("Error creating DocumentSymbol, 'name' not found in dct")
        self.name: str = self.symbol #just an alias for self.symbol
        self.uri = uri
        self.buffer = open_buffers[uri]
        range_dct = dct.get('range', {})
        if not range_dct:
            raise RuntimeError("Error creating DocumentSymbol, 'range' not found in dct")
        selection_range_dct = dct.get('selectionRange', {})
        if not selection_range_dct:
            raise RuntimeError("Error creating DocumentSymbol, 'selectionRange' not found in dct")
        self.range: Selection = selection_from_dict(range_dct)
        self.start: Position = self.range.start
        self.end  : Position = self.range.end
        self.selectionRange: Selection = selection_from_dict(selection_range_dct)
        self.kind: int = dct.get('kind', -1)
        if self.kind == -1:
            raise RuntimeError("Error creating DocumentSymbol, 'kind' not found in dct")
        self.parent: DocumentSymbol|None = parent
        self.children: list[DocumentSymbol] = [DocumentSymbol(child, uri, self) for child in dct.get('children', [])]
        self.context_str = '/'.join(self.get_full_context())

    def contains(self, pos: Position) -> bool:
        '''Returns `True` if `pos` is contained in self.range, otherwise returns `False`'''
        start   = (self.start.line, self.start.col)
        end     = (self.end.line, self.end.col)
        current = (pos.line, pos.col)
        return start <= current < end


    def get_symbol_containing(self, pos: Position):
        curr_ds: DocumentSymbol = self
        if not curr_ds.contains(pos):
            return None

        while curr_ds.contains(pos):
            if not curr_ds.children:
                break
            found_container = False
            for ds in curr_ds.children:
                if ds.contains(pos):
                    curr_ds = ds
                    found_container = True
                    break
            if not found_container:
                break
        return curr_ds

    def get_full_context(self):
        '''
        Returns the chain from this symbol to the top level of the document it's in.
        In other words it turns a list like `[self, self.parent, self.parent.parent, ...][::-1]`
        '''
        context: list[str] = []
        curr: DocumentSymbol = self
        while curr is not None:
            context.append(curr.name)
            if curr.parent is not None:
                curr = curr.parent
            else:
                break
        return context

    def as_dict(self):
        return {'name': self.name, 'range': self.range.as_dict(), 'selectionRange': self.selectionRange.as_dict(),
                'kind': self.kind, 'children': [child.as_dict() for child in self.children]}

    def __str__(self):
        return str(self.as_dict())

    def __repr__(self):
        return str(self)







class Buffer:
    def __init__(self, msg: Message):
        self.uri:      str = msg.get('params', 'textDocument', 'uri')
        self.path:     str = uri_to_path(self.uri)
        self.filename: str = self.path.split('/')[-1]
        self.dup_path: str = os.path.join(user_home_local, 'tmp', 'openbuffers', self.filename)
        self.text:     str = msg.get('params', 'textDocument', 'text', default_value='')
        # Getting document symbols requires sending a LSP message to sourcekit-lsp, so it cannot be done synchonously
        # So here we declare self.document_symbols as an empty list, and then send off a textDocument/documentSymbol request
        # for this buffer to sourcekit-lsp.   self.document_symbols will then get updated in sourcekit_lsp_proxy.py inside of
        self.document_symbols: list[DocumentSymbol] = []
        self.last_change_time = time.monotonic()
        self.needs_ds_update = True
        self.ds_update_in_flight = False


        if not self.text:
            with open(self.path, 'r') as f:
                self.text = f.read()
        self.lines: list[str] = self.text.splitlines(keepends=True)
        with open(self.dup_path, 'wb') as f:
            f.write(self.text.encode())

        if self.lines:
            if self.lines[0]:
                self.line_endings = CRLF if self.lines[0].endswith(CRLF) else LF
            else:
                self.line_endings = CRLF
        else:
            self.line_endings = CRLF

        # self.line_endings = CRLF if self.lines[0].endswith()


    def get_line_start_pos(self, line_number: int) -> int:
        '''
        Returns the character offset in self.text required to be at line number `line`
        '''
        blank_lines_before = len([line for line in self.lines[:line_number+1] if line in ['', '\n', '\r\n']])
        pos = 0
        for i, line in enumerate(self.lines):
            if i == line_number:
                return pos
                # return self.text.find(line)
            pos += len(line)
        raise RuntimeError('Unknown error getting line start pos.  You just gotta fix the Buffer.get_line_start_pos() method')

    def get_offset(self, pos: Position) -> int:
        return self.get_line_start_pos(pos.line) + pos.col


    def apply_change(self, change: dict, update_dup: bool = True):
        rnge_dct = change.get('range', {})
        if not rnge_dct:
            raise RuntimeError(f"Error, 'range' key not found in given change: {change}")
        rnge = selection_from_dict(change)
        text: str = str(change.get('text', None))
        if text is None:
            raise RuntimeError(f"Error, 'text' key not found in given change: {change}")
        start = rnge.start
        end = rnge.end
        start_pos = self.get_line_start_pos(start.line) + start.col
        end_pos = self.get_line_start_pos(end.line) + end.col
        #update self.text with the new text
        self.text = self.text[:start_pos] + text + self.text[end_pos:]

        # update self.lines
        self.lines = self.text.splitlines(keepends=True)
        if update_dup:
            with open(self.dup_path, 'wb') as f:
                f.write(self.text.encode())


    def apply_didchange_message(self, msg: Message, update_last_change_time=True):
        changes: list[dict] = msg.get('params', 'contentChanges', default_value=[])
        for change in changes:
            self.apply_change(change, update_dup=True)
        if update_last_change_time:
            self.last_change_time = time.monotonic()
            self.needs_ds_update = True

    def get_symbol_containing(self, pos: Position) -> DocumentSymbol|None:
        '''Returns the innermost DocumentSymbol associated with this Buffer which contains `pos`'''
        for ds in self.document_symbols:
            if ds.contains(pos):
                return ds.get_symbol_containing(pos)
        return None



    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return self.text.replace('\r', '\\r').replace('\n', '\\n')



def close_buffer(uri: str):
    log_unmissable(f'CLOSING BUFFER FOR URI: {uri}')
    if isinstance(uri, Buffer):
        uri = uri.uri
    if uri in open_buffers:
        buf = open_buffers[uri]
        os.remove(buf.dup_path)
        del open_buffers[uri]
    else:
        log(f'ATTEMPTED TO CLOSE BUFFER WITH URI: {uri} WHICH WAS NOT FOUND IN open_buffers')




def document_symbols_from_message(msg: Message, uri: str) -> list[DocumentSymbol]:
    if not 'result' in msg.dct:
        if 'error' in msg.dct:
            return []
        raise RuntimeError(f"Error, 'result' not found in textDocument/documentSymbol response: {msg.dct}")
    results: list[dict] = msg.get('result')
    document_symbols = [DocumentSymbol(ds_dct, uri) for ds_dct in results]
    return document_symbols

open_buffer_count = 0
open_buffers: dict[str, Buffer] = {}

# main for testing
if __name__ == '__main__':
    dct = {"params":{"textDocument":{"languageId":"swift","version":0,"uri":"file:///C:/Users/sjber/Coding/iOS/iosapptest2/iosapptest2/App.swift","text":"import SwiftUI\r\n\r\n@main\r\nstruct iosapptest2App: App {  //start of a comment end of a comment\r\n    var body: some Scene {\r\n        WindowGroup {\r\n            ContentView()\r\n        }\r\n    }\r\n}\r\n"}},"jsonrpc":"2.0","method":"textDocument/didOpen"}
    msg = Message(dct)
    buf = Buffer(msg)
    changedct = {"params":{"textDocument":{"version":4,"uri":"file:///C:/Users/sjber/Coding/iOS/iosapptest2/iosapptest2/App.swift"},"contentChanges":[{"rangeLength":2,"range":{"end":{"character":0,"line":5},"start":{"character":26,"line":4}},"text":"\r\n        \r\n"}]},"jsonrpc":"2.0","method":"textDocument/didChange"}
    change_msg = Message(changedct)
    changes = change_msg.get('params', 'contentChanges')
    change = changes[0]



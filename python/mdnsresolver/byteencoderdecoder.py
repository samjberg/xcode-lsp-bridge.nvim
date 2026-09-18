import struct
from typing import Literal
from math import log, ceil
from .utils import *

powers_of_256: list[int] = [256**i for i in range(16)]


def get_next_pow256(x: int) -> int:
    '''
    Returns the next power of 256 that is larger than x
    '''
    for p in powers_of_256:
        if p > x:
            return p
    return 0

# I refuse to explain myself, this just works
def get_min_bytelength(x: int) -> int:
    '''
    Returns the minimum number of bytes required to represent x.  Works for both signed and unsigned ints
    '''
    if x > 0:
        return powers_of_256.index(get_next_pow256(x))
    return powers_of_256.index(get_next_pow256(abs((x+1)*2)))


def bits(x: int, bytewidth: int):
    return format(x & ((1 << (bytewidth*8)) - 1), f'0{bytewidth*8}b')

def int_to_binstr(x: int, ensure_full_bytes: bool = True):
    is_negative: bool = x < 0
    if not is_negative:
        bs: str = bin(x)[2:]
    else:
        bs: str = bin(x)[3:]
    min_bytelength = get_min_bytelength(x)
    if ensure_full_bytes:
        bs = '0'*((8*min_bytelength)-len(bs)) + bs

    if is_negative:
        bs = '-' + bs
    return bs

def binstr_to_int(bs: str):
    if bs.startswith('0b'):
        bs = bs[2:]
    return int(bs, 2)

def flip_bits(x: int, bitlength: int = 0):
    '''
    Flips the bits of x such that all 1s become 0s, and all 0s become 1s, in the binary representation of x
    '''
    if bitlength == 0:
        bitlength = get_min_bytelength(x) * 8
    return x ^ (2**bitlength - 1)


class ByteEncoder:
    def __init__(self, byteorder: Literal['big', 'little'] = 'big'):
        self.byteorder: Literal['big', 'little'] = byteorder
        self.bytes: bytes = b''

    def encode_int(self, x: int, length: int = 0, signed: bool = False, byteorder: Literal['auto', 'big', 'little'] = 'auto') -> None:
        byteorder = byteorder if byteorder != 'auto' else self.byteorder
        if length == 0:
            length = get_min_bytelength(x)
        # If signed is False but x < 0, automatically change signed to True
        if not signed and x<0:
            signed = True
        self.bytes += x.to_bytes(length, byteorder, signed=signed)


    def encode_str(self, s: str, length: int = 0, encoding: str = 'utf-8'):
        b = s.encode(encoding)
        # print(f'b: {b}')
        if length == 0:
            length = len(b)
        elif length < 0:
            raise ValueError(f'Error, length must be >= 0, got length: {length}')

        # print(f'length: {length}')
        if self.byteorder == 'big':
            b = bytes(length - len(b)) + b
        else:
            b += bytes(length - len(b))
        self.bytes += b

    def encode_float(self, x: float):
        self.bytes += struct.pack('f', x) 

    def encode_double(self, x: float):
        self.bytes += struct.pack('d', x)

    def encode_bitstr(self, bs: str, ignore_byteorder: bool = False):
        if bs.startswith('0b'):
            bs = bs[2:]

        length = len(bs)

        if not ((length % 8) == 0):
            raise ValueError(f'Error, bitstring must have a length which is a multiple of 8.  Got bitstring with length: {len(bs)}')

        bytelength = length // 8

        x = int(bs, 2)
        # if respect_byteorder is False, we run encode_int with byteorder='big' to override whatever the ByteEncoder's
        # actual byteorder might be.  This ensures that the bytes that get written to self.bytes will be representing
        # the exact bitstring in the exact order that `bs` shows
        if ignore_byteorder:
            self.encode_int(x, length=bytelength, byteorder='big')
        # Otherwise, we just run self.encode_int normally, and self.byteorder will be used
        else:
            self.encode_int(x, length=bytelength)

    def set_bytes(self, b: bytes, idx: int):
        length: int = len(b)
        self.bytes = self.bytes[:idx] + b + self.bytes[idx+length:]

    def __str__(self):
        return str(self.bytes)

    def __repr__(self):
        return repr(self.bytes)



class ByteDecoder:
    def __init__(self, b: bytes, byteorder: Literal['little', 'big'] = 'big', default_length_prefix_size: int = 1):
        self.bytes: bytes = b
        self.total_length: int = len(self.bytes)
        self.byteorder: Literal['little', 'big'] = byteorder
        self.pos: int = 0
        self.default_length_prefix_size: int = default_length_prefix_size

    def bytes_remaining(self) -> int:
        return self.total_length - self.pos

    def get_next_bytes(self, num_bytes: int):
        if (self.pos + num_bytes) > self.total_length:
            raise RuntimeError(f'Error, getting the next: {num_bytes} bytes would overrun self.bytes.  Only {self.bytes_remaining()} bytes remaining')

        b: bytes = self.bytes[self.pos: self.pos + num_bytes]
        self.pos += num_bytes
        return b

    def peek_next_bytes(self, num_bytes: int) -> bytes:
        if (self.pos + num_bytes) > self.total_length:
            raise RuntimeError(f'Error, peeking the next: {num_bytes} bytes would overrun self.bytes')
        return self.bytes[self.pos: self.pos + num_bytes]

    def decode_int(self, length: int = 1, signed: bool = False):
        b = self.get_next_bytes(length)
        return int.from_bytes(b, self.byteorder, signed=signed)

    def decode_str(self, length: int):
        s = self.get_next_bytes(length).decode()
        # print(f'decoded str: {s}')
        return s

    def decode_length_prefixed_str(self, length_prefix_size: int = 0):
        if length_prefix_size == 0:
            length_prefix_size = self.default_length_prefix_size

        length = self.decode_int(length_prefix_size)
        return self.decode_str(length)

    # def decode_




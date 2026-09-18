import os, sys, socket, time
from typing import Any, Callable, Literal, Iterable
from random import randint
import re

# local_port = 30523
netex_root = os.sep.join(__file__.split(os.sep)[:-1])

def segment_iterable(lst: list[Any]|str|bytes, groupsize: int = 2) -> list[list[Any]|str|bytes]:
    length: int = len(lst)
    segments: list[list|str|bytes] = []
    for i in range(0, length, groupsize):
        if (i+groupsize) > length:
            seg = lst[i:]
            segments.append(seg)
            break
        else:
            seg = lst[i:i+groupsize]
            segments.append(seg)
    return segments

def segment_iterable_n_groups(lst: list|str, num_groups: int = 2):
    groupsize = len(lst)//num_groups
    return segment_iterable(lst, groupsize)


def invert_dict(dct: dict[Any, Any]) -> dict[Any, Any]:
    '''Inverts a dict, flipping key:value pairs to be value:key pairs in the output.
       So for example a `dict[str, int]` will become a `dict[int, str]`
    '''
    return {val:key for key, val in dct.items()}




def apply(f: Callable, lst: list[Any]) -> list[Any]:
    return [f(x) for x in lst]




def normalize_path(path: str, sep='/', strip_drive=False) -> str:
    if strip_drive:
        path = os.path.splitdrive(path)[1]
    if sep == '/':
        return path.replace('\\', '/')
    elif sep == '\\':
        return path.replace('/', '\\')
    raise RuntimeError(f"Invalid separator, must be '/' or '\\'.  Offending path: {path}")

def join_paths(root_path: str, *paths: str):
    joined_path = root_path
    for path in paths:
        if path.startswith('/') or path.startswith('\\'):
            path = path[1:]
        joined_path = normalize_path(os.path.join(joined_path, path))
    return joined_path



def path_depth(path: str):
    return len([part for part in normalize_path(path, strip_drive=True).split('/') if part])

def get_project_root_path(path: str = '') -> str:
    if not path:
        path = os.getcwd()

    curr_path = path
    # os.listdir(curr_path)

    while not '.git' in os.listdir(curr_path) and (path_depth(curr_path) > 0):
        input(curr_path)
        curr_path = os.path.split(curr_path)[0]
    return curr_path



def display_bytes_unencoded(b: bytes):
    s: str = ''
    for x in b:
        h = '\\' + hex(x)[1:]
        digits = h[2:]
        if len(digits) == 1:
            digits = '0' + digits
        digits = '\\x' + digits
        s += digits
    s = f"b'{s}'"
    print(s)



def get_factors(x: int):
    factors: list[int] = []
    for i in range(2, x//2 + 1):
        if x % i == 0:
            factors.append(i)
    return factors

def find_nth_occurence(s: str, c: str, n: int):
    '''
    Returns the index of the `n`th occurence of `c` in `s`
    For example `find_nth_occurence('hello there bob', 'e', 3)`
    returns 10, because the final 'e' in 'there' is the 3rd occurence
    of 'e' in 'hello there bob', and it occurs at index 10, so 10 is returned
    '''
    if not c in s:
        return -1
    i: int = 0
    count: int = 0
    while count < n:
        i = s.find(c, i+1)
        if i == -1:
            return i
        count += 1
    return i


def reverse_ip_segments(ip: str):
    return '.'.join(ip.split('.')[::-1])


def is_ipv6_addr(ip: str):
    parts: list[str] = ip.split(':')
    if len(parts) != 8 and all(parts):
        # If there are NOT 8 parts AND it IS true that all the parts are non-empty, then it cannot be a valid ipv6 address
        return False
    ipv6_part_pattern: str = r'[a-zA-Z0-9]{1,4}'
    for part in parts:
        if not re.match(ipv6_part_pattern, part):
            return False
    return True





def get_ip_type(ip: str) -> Literal['ipv4', 'ipv6', 'invalid_ip']:
    '''Returns whether `ip` is IPv4 or IPv6'''
    ipv4_pattern = r'\d{1,3}(\.\d{1-3}){3}'
    ipv6_pattern = r'[a-zA-Z0-9]{1,4}:[a-zA-Z0-9]{1,4}:[a-zA-Z0-9]{1,4}:[a-zA-Z0-9]{1,4}:[a-zA-Z0-9]{1,4}:[a-zA-Z0-9]{1,4}:[a-zA-Z0-9]{1,4}:[a-zA-Z0-9]{1,4}'
    if re.match(ipv4_pattern, ip):
        return 'ipv4'
    elif re.match(ipv6_pattern, ip):
        return 'ipv6'
    
    return 'invalid_ip'


ip_sort_key: Callable = lambda ip: int(ip.split('.')[-1])





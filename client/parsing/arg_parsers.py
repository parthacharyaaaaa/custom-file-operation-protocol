'''Parsers for individual arguments'''

import re
from models.constants import REQUEST_CONSTANTS

def parse_filename(filename: str) -> str:
    if not re.match(r'(.\w*)+', (filename:=filename.strip())):
        raise ValueError('Invalid filename')
    return filename

def parse_dir(dir: str) -> str:
    if not (dir:=dir.strip()).isalnum():
        raise ValueError('Invalid directory name')
    return dir

def parse_non_negative_int(arg: str) -> int:
    if not (arg:=arg.strip()).isnumeric():
        raise ValueError(f'Non-numeric argument ({arg}) given')
    num: int = int(arg)
    if num < 0:
        raise ValueError(f'Non-negative integer expected, got ({num})')
    return num

def parse_host_arg(host: str) -> str:
    if not re.match(r'^((25[0-5]|(2[0-4]|1\d|[1-9]|)\d)\.?\b){4}$', host):
        raise ValueError(f'Invalid IP (v4/v6) address {host} provided')
    return host

def parse_port_arg(arg: str) -> int:
    if not arg.isnumeric():
        raise TypeError('Port must be numeric')
    
    port: int = int(arg)
    if not (0 <= port <= 65_535):
        raise ValueError('TCP port must be between range 0 and 65,535')
    
    return port

def parse_password_arg(arg: str) -> str:
    if not (REQUEST_CONSTANTS.auth.password_range[0] <= len(arg) <= REQUEST_CONSTANTS.auth.password_range[1]):
        raise ValueError(f'Invalid range for password ({len(arg)}), must be in range {REQUEST_CONSTANTS.auth.password_range}')
    
    return arg

def parse_username_arg(arg: str) -> str:
    arg = arg.strip()
    if not (REQUEST_CONSTANTS.auth.username_range[0] <= len(arg) <= REQUEST_CONSTANTS.auth.username_range[1]):
        raise ValueError(f'Invalid range for password ({len(arg)}), must be in range {REQUEST_CONSTANTS.auth.username_range}')
    
    if not re.match(REQUEST_CONSTANTS.auth.username_regex, arg):
        raise ValueError(f'Invalid username format: {arg}')
        
    return arg

def parse_write_data(arg: str) -> memoryview:
    return memoryview(arg.encode('utf-8'))
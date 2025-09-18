'''Parsers for individual arguments'''

import re
from pathlib import Path
from typing import TYPE_CHECKING

from client.cmd.commands import QueryTypes, QueryMapper

from models.constants import REQUEST_CONSTANTS
from models.permissions import RoleTypes
from models.flags import InfoFlags

if TYPE_CHECKING: assert REQUEST_CONSTANTS

__all__ = (
    "parse_filename",
    "parse_dir",
    "parse_filepath",
    "parse_non_negative_int",
    "parse_host_arg",
    "parse_port_arg",
    "parse_password_arg",
    "parse_username_arg",
    "parse_write_data",
    "parse_chunk_size",
    "parse_grant_duration",
    "parse_granted_role",
    "parse_query_type",
)


def parse_filename(filename: str) -> str:
    if not re.match(r'(.\w*)+', (filename:=filename.strip())):
        raise ValueError('Invalid filename')
    return filename

def parse_dir(dir: str) -> str:
    if not (dir:=dir.strip()).isalnum():
        raise ValueError('Invalid directory name')
    return dir

def parse_filepath(fpath_arg: str) -> Path:
    fpath: Path = Path(fpath_arg)
    if not fpath.is_file():
        raise FileNotFoundError(f'{fpath_arg} not found in local file system')
    return fpath

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

def parse_chunk_size(arg: str) -> int:
    if not arg.isnumeric():
        raise ValueError(f'Non-numeric value given for chunk size: {arg}')
    chunk_size: int = int(arg)
    if chunk_size <= 0:
        raise ValueError('Chunk size must be a positive integer')
    
    return min(REQUEST_CONSTANTS.file.chunk_max_size, chunk_size)

def parse_grant_duration(arg: str) -> int:
    if not arg.isnumeric():
        raise ValueError(f'Non-numeric value given for chunk size: {arg}')
    duration: int = int(arg)
    if not REQUEST_CONSTANTS.permission.effect_duration_range[0] < duration < REQUEST_CONSTANTS.permission.effect_duration_range[1]:
        raise ValueError(f'Permission effect duration must be between {REQUEST_CONSTANTS.permission.effect_duration_range}, got: {duration}')
    return duration

def parse_granted_role(arg: str) -> RoleTypes:
    try:
        role_type: RoleTypes = RoleTypes(arg.lower())
        if role_type == RoleTypes.OWNER:
            raise TypeError(f'Owner role cannot be granted using the GRANT command')
        return role_type
    except ValueError:
        raise ValueError('Invalid role type provided')
    
def parse_query_type(arg: str) -> InfoFlags:
    try:
        query_type: QueryTypes = QueryTypes(arg)
        return QueryMapper[query_type]
    except ValueError:
        raise ValueError(f'Invalid query type provided (arg), should be in: {(member.value for member in QueryTypes._member_map_.values())}')
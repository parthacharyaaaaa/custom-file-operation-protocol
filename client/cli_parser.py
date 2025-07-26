import argparse
import re
import warnings

from models.constants import REQUEST_CONSTANTS

__all__ = ('PARSER', 'parse_args')

def _parse_host_arg(host: str) -> str:
    if not re.match(r'^((25[0-5]|(2[0-4]|1\d|[1-9]|)\d)\.?\b){4}$', host):
        raise ValueError(f'Invalid IP (v4/v6) address {host} provided')
    return host

def _parse_port_arg(arg: str) -> int:
    if not arg.isnumeric():
        raise TypeError('Port must be numeric')
    
    port: int = int(arg)
    if not (0 <= port <= 65_535):
        raise ValueError('TCP port must be between range 0 and 65,535')
    
    return port

def _parse_password_arg(arg: str) -> str:
    if not (REQUEST_CONSTANTS.auth.password_range[0] <= len(arg) <= REQUEST_CONSTANTS.auth.password_range[1]):
        raise ValueError(f'Invalid range for password ({len(arg)}), must be in range {REQUEST_CONSTANTS.auth.password_range}')
    
    return arg

def _parse_username_arg(arg: str) -> str:
    arg = arg.strip()
    if not (REQUEST_CONSTANTS.auth.username_range[0] <= len(arg) <= REQUEST_CONSTANTS.auth.username_range[1]):
        raise ValueError(f'Invalid range for password ({len(arg)}), must be in range {REQUEST_CONSTANTS.auth.username_range}')
    
    if not re.match(REQUEST_CONSTANTS.auth.username_regex, arg):
        raise ValueError(f'Invalid username format: {arg}')
        
    return arg

PARSER: argparse.ArgumentParser = argparse.ArgumentParser(prog='Client tool for whatever this protocol is named idk')
### CLI arguments ###
PARSER.add_argument('--host', '-H',
                    help='The host machine to connect to',
                    type=_parse_host_arg, required=True)

PARSER.add_argument('--port', '-P',
                    help='The port of the target process',
                    type=_parse_port_arg, required=True)

PARSER.add_argument('--username', '-U',
                    help='Optional username value used to start a remote session alongside the shell',
                    required=False, type=_parse_username_arg, default=None)

PARSER.add_argument('--password', '-PS',
                    help='Optional password value used to start a remote session alongside the shell',
                    required=False, type=_parse_password_arg, default=None)

def parse_args() -> argparse.Namespace:
    args: argparse.Namespace = PARSER.parse_args()

    if (bool(args.username) ^ bool(args.password)):
        raise ValueError('Partial credentials provided. If authenticating outside of the client shell, both username and password flags must be provided')
    
    if args.password:
        warnings.warn('It is not recommended to enter credentials outside of the client shell, instead use the AUTH command within the shell itself',
                      category=UserWarning)
    
    return args
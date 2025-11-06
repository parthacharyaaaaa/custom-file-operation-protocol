'''Module containing argument parsing logic for client entrypoint'''

import argparse
import warnings
from typing import Final

from client.parsing.explicit_argument_parser import ExplicitArgumentParser
from client.parsing.arg_parsers import parse_host_arg, parse_port_arg, parse_username_arg, parse_password_arg

__all__ = ('ENTRYPOINT_PARSER', 'parse_args')

ENTRYPOINT_PARSER: Final[ExplicitArgumentParser] = ExplicitArgumentParser(prog='client',
                                                                          description="Client shell")
ENTRYPOINT_PARSER.add_argument('host',
                               help='The host machine to connect to',
                               type=parse_host_arg)

ENTRYPOINT_PARSER.add_argument('port',
                               help='The port of the target process',
                               type=parse_port_arg)

ENTRYPOINT_PARSER.add_argument('--username', '-u',
                               help='Optional username value used to start a remote session alongside the shell',
                               required=False, type=parse_username_arg, default=None)

ENTRYPOINT_PARSER.add_argument('--password', '-p',
                               help='Optional password value used to start a remote session alongside the shell',
                               required=False, type=parse_password_arg, default=None)

ENTRYPOINT_PARSER.add_argument('--blind-trust', '-bt',
                               help="Blindly trust a remote server, even when it's provided certificate does not match the one stored",
                               default=False, action='store_true')

def parse_args() -> argparse.Namespace:
    args: argparse.Namespace = ENTRYPOINT_PARSER.parse_args()

    if (bool(args.username) ^ bool(args.password)):
        raise ValueError('Partial credentials provided. If authenticating outside of the client shell, both username and password flags must be provided')
    
    return args
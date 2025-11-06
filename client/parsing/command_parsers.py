'''Parsers for client shell's commands'''
import argparse
from typing import Final, TYPE_CHECKING

from client.parsing.explicit_argument_parser import ExplicitArgumentParser
from client.cmd.commands import GeneralModifierCommands, AuthModifierCommands, FileModifierCommands, PermissionModifierCommands
from client.parsing import arg_parsers

from models.constants import REQUEST_CONSTANTS

if TYPE_CHECKING: assert REQUEST_CONSTANTS

__all__ = ('generic_modifier_parser', 'file_command_parser', 'permission_command_parser', 'auth_command_parser')

generic_modifier_parser: Final[ExplicitArgumentParser] = ExplicitArgumentParser(prog='modifier_commands',
                                                                                add_help=False)
for modifier in GeneralModifierCommands:
    generic_modifier_parser.add_argument(f'-{modifier.value.lower()}', help=None, action='store_true')

#NOTE: For the generic filedir_parser, the action for 'directory' will have a default value injected at runtime based on the remote session
filedir_parser: Final[ExplicitArgumentParser] = ExplicitArgumentParser(prog='filedir_parser', parents=[generic_modifier_parser], add_help=False)
filedir_parser.add_argument('file', type=arg_parsers.parse_filename)
filedir_parser.add_argument('directory', type=arg_parsers.parse_dir)

local_filedir_parser: Final[ExplicitArgumentParser] = ExplicitArgumentParser(prog='local_filedir_parser', parents=[generic_modifier_parser], add_help=False)
local_filedir_parser.add_argument('local_filepath', type=arg_parsers.parse_filepath)
local_filedir_parser.add_argument('remote_filename', type=arg_parsers.parse_filename)
local_filedir_parser.add_argument('remote_directory', type=arg_parsers.parse_dir)
local_filedir_parser.add_argument(f'--{FileModifierCommands.CHUNK_SIZE.value}', required=False, type=arg_parsers.parse_chunk_size, default=REQUEST_CONSTANTS.file.chunk_max_size)
local_filedir_parser.add_argument(f'--{FileModifierCommands.POSITION.value}', required=False, type=arg_parsers.parse_non_negative_int)
local_filedir_parser.add_argument(f'--{FileModifierCommands.POST_OPERATION_CURSOR_KEEPALIVE.value}', required=False, action='store_true', default=False)

### File operations ###
file_command_parser: Final[ExplicitArgumentParser] = ExplicitArgumentParser(prog='file_command_parser', parents=[filedir_parser], add_help=False)
file_command_parser.add_argument(FileModifierCommands.WRITE_DATA.value, default=memoryview(b''), type=arg_parsers.parse_write_data)

### INFO operations ###
info_command_parser: Final[ExplicitArgumentParser] = ExplicitArgumentParser(prog='info_command_parser', parents=[generic_modifier_parser], add_help=False)
info_command_parser.add_argument('query_type', type=arg_parsers.parse_query_type)
info_command_parser.add_argument('resource_name')
info_command_parser.add_argument('--verbose', action='store_true')

added_action = next(filter(lambda action : action.dest == 'resource_name', info_command_parser._actions))
added_action.required = False

# Awful hack alert
added_action = next(filter(lambda action : action.dest == FileModifierCommands.WRITE_DATA.value, file_command_parser._actions))
added_action.required = False

file_command_parser.add_argument(f'--{FileModifierCommands.CHUNK_SIZE.value}', required=False, type=arg_parsers.parse_chunk_size, default=REQUEST_CONSTANTS.file.chunk_max_size)
file_command_parser.add_argument(f'--{FileModifierCommands.LIMIT.value}', required=False, type=arg_parsers.parse_non_negative_int)
file_command_parser.add_argument(f'--{FileModifierCommands.POSITION.value}', required=False, type=arg_parsers.parse_non_negative_int)
file_command_parser.add_argument(f'--{FileModifierCommands.CHUNKED.value}', required=False, action='store_true', default=True)
file_command_parser.add_argument(f'--{FileModifierCommands.POST_OPERATION_CURSOR_KEEPALIVE.value}', required=False, action='store_true', default=False)

### Permission operations ###
permission_command_parser: Final[ExplicitArgumentParser] = ExplicitArgumentParser(prog='permission_command_parser', parents=[filedir_parser], add_help=False)
permission_command_parser.add_argument('user', type=arg_parsers.parse_username_arg, default=None)
permission_command_parser.add_argument('role', type=arg_parsers.parse_granted_role)

role_action: argparse.Action = next(filter(lambda action : action.dest == 'role', permission_command_parser._actions))
role_action.default = None
role_action.required = False

permission_command_parser.add_argument('--duration', type=arg_parsers.parse_grant_duration, default=REQUEST_CONSTANTS.permission.effect_duration_range[0])
for permisison_modifier in PermissionModifierCommands:
    permission_command_parser.add_argument(f'-{permisison_modifier.value.lower()}', help=None, action='store_true')

### Auth operations ###

auth_command_parser: Final[ExplicitArgumentParser] = ExplicitArgumentParser(prog='auth_command_parser', parents=[generic_modifier_parser], add_help=False)
auth_command_parser.add_argument('username', type=arg_parsers.parse_username_arg)
auth_command_parser.add_argument('password', type=arg_parsers.parse_password_arg)

for auth_modifier in AuthModifierCommands:
    auth_command_parser.add_argument(f'-{auth_modifier.value.lower()}', help=None, action='store_true')

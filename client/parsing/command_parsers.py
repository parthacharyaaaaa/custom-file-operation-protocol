'''Parsers for client shell's commands'''
import argparse

from client.parsing.explicit_argument_parser import ExplicitArgumentParser
from client.cmd.commands import GeneralModifierCommands, FileModifierCommands, AuthModifierCommands, PermissionModifierCommands
from client.parsing import arg_parsers

from models.constants import REQUEST_CONSTANTS

__all__ = ('generic_modifier_parser', 'file_command_parser', 'permission_command_parser', 'auth_command_parser')

generic_modifier_parser: ExplicitArgumentParser = ExplicitArgumentParser(prog='modifier_commands')
for modifier in GeneralModifierCommands:
    generic_modifier_parser.add_argument(f'-{modifier.value.lower()}', help=None, action='store_true')

#NOTE: For the generic filedir_parser, the action for 'directory' will have a default value injected at runtime based on the remote session
filedir_parser: ExplicitArgumentParser = ExplicitArgumentParser(prog='filedir_parser', parents=[generic_modifier_parser], add_help=False)
filedir_parser.add_argument('file', type=arg_parsers.parse_filename)
filedir_parser.add_argument('directory', type=arg_parsers.parse_dir)

### File operations ###

file_command_parser: ExplicitArgumentParser = ExplicitArgumentParser(prog='file_command_parser', parents=[filedir_parser], add_help=False)
file_command_parser.add_argument('write_data', default=memoryview(b''), type=arg_parsers.parse_write_data)

# Awful hack alert
added_action = next(filter(lambda action : action.dest == 'write_data', file_command_parser._actions))
added_action.required = False

file_command_parser.add_argument('--chunk-size', required=False, type=arg_parsers.parse_chunk_size, default=REQUEST_CONSTANTS.file.chunk_max_size)
file_command_parser.add_argument('--limit', required=False, type=arg_parsers.parse_non_negative_int)
file_command_parser.add_argument('--pos', required=False, type=arg_parsers.parse_non_negative_int, default=0)
file_command_parser.add_argument('--chunked', required=False, action='store_true', default=True)

for file_modifier in FileModifierCommands:
    file_command_parser.add_argument(f'-{file_modifier.value.lower()}', help=None, action='store_true')

### Permission operations ###

permission_command_parser: ExplicitArgumentParser = ExplicitArgumentParser(prog='permission_command_parser', parents=[filedir_parser], add_help=False)
permission_command_parser.add_argument('user', type=arg_parsers.parse_username_arg, default=None)
permission_command_parser.add_argument('role', type=arg_parsers.parse_granted_role)

role_action: argparse.Action = next(filter(lambda action : action.dest == 'role', permission_command_parser._actions))
role_action.default = None
role_action.required = False

permission_command_parser.add_argument('--duration', type=arg_parsers.parse_grant_duration, default=REQUEST_CONSTANTS.permission.effect_duration_range[0])
for permisison_modifier in PermissionModifierCommands:
    permission_command_parser.add_argument(f'-{permisison_modifier.value.lower()}', help=None, action='store_true')

### Auth operations ###

auth_command_parser: ExplicitArgumentParser = ExplicitArgumentParser(prog='auth_command_parser', parents=[generic_modifier_parser], add_help=False)
auth_command_parser.add_argument('username', type=arg_parsers.parse_username_arg)
auth_command_parser.add_argument('password', type=arg_parsers.parse_password_arg)

for auth_modifier in AuthModifierCommands:
    auth_command_parser.add_argument(f'-{auth_modifier.value.lower()}', help=None, action='store_true')

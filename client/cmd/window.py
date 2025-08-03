import asyncio
import argparse
import functools
import shlex
from typing import Optional, Callable, Any

from client import session_manager
from client.cmd import async_cmd
from client.parsing import command_parsers
from client.cmd import operational_utils as op_utils
from client.cmd import errors as cmd_errors 
from client.config import constants as client_constants
from client.operations import auth_operations, file_operations, permission_operations, info_operations

from models.constants import REQUEST_CONSTANTS
from models.request_model import BaseAuthComponent, BaseFileComponent, BasePermissionComponent

class ClientWindow(async_cmd.AsyncCmd):
    def inject_default_dirname(self) -> None:
        for action in command_parsers.filedir_parser._actions:
            if action.dest == 'directory':
                action.default = self.session_master.identity
                action.required = False
                break

    # Overrides
    def __init__(self, host: str, port: int,
                 reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 client_config: client_constants.ClientConfig, session_master: session_manager.SessionManager,
                 completekey = "tab", stdin = None, stdout = None):
        
        self.reader: asyncio.StreamReader = reader
        self.writer: asyncio.StreamWriter = writer
        self.client_config: client_constants.ClientConfig = client_config
        self.session_master: session_manager.SessionManager = session_master
        self.connection_ended: bool = False

        # Update filedir argument parser to include default value of directory as user identity
        self.inject_default_dirname()

        self.prompt = f'{host}:{port}>'
        super().__init__(completekey, stdin, stdout)
    
    # Decorators
    def require_auth_state(state: bool):
        def outer_wrapper(method: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(method)
            def inner_wrapper(*args, **kwargs):
                session_master: session_manager.SessionManager = getattr(args[0], 'session_master', None)
                if not (session_master and bool(session_master.identity) == state):
                    raise cmd_errors.InvalidAuthenticationState
                
                return method(*args, **kwargs)
            return inner_wrapper
        return outer_wrapper

    # Methods
    async def do_heartbeat(self, args: str) -> None:
        '''
        HEARTBEAT [modifiers]
        Send a heartbeat signal to the connected process
        '''
        parsed_args: argparse.Namespace = command_parsers.generic_modifier_parser.parse_args(args.split())
        self.end_connection = parsed_args.bye
        await info_operations.send_heartbeat(reader=self.reader, writer=self.writer,
                                             client_config=self.client_config, session_master=self.session_master,
                                             end_connection=self.end_connection)

    @require_auth_state(state=False)
    async def do_auth(self, args: str) -> None:
        '''
        AUTH [username] [password] [MODIFIERS]
        Start a remote session on the host machine.
        This is the recommended way of starting a remote session, as it avoids writing password to shell history'''
        parsed_args: argparse.Namespace = command_parsers.auth_command_parser.parse_args(args.split())
        auth_component: BaseAuthComponent = await op_utils.make_auth_component(parsed_args.username, parsed_args.password)
        
        self.end_connection = parsed_args.bye
        await auth_operations.authorize(reader=self.reader, writer=self.writer,
                                        auth_component=auth_component,
                                        client_config=self.client_config, session_manager=self.session_master,
                                        display_credentials=parsed_args.dc, end_connection=self.end_connection)
        self.inject_default_dirname()

    @require_auth_state(state=True)
    async def do_sterm(self, args: str) -> None:
        '''
        STERM [MODIFIERS]
        Terminate an established remote session
        '''
        parsed_args: argparse.Namespace = command_parsers.generic_modifier_parser.parse_args(args.split())
        display_credentials, self.end_connection = parsed_args.dc, parsed_args.bye
        await auth_operations.end_remote_session(reader=self.reader, writer=self.writer,
                                                 client_config=self.client_config, session_manager=self.session_master,
                                                 display_credentials=display_credentials, end_connection=self.end_connection)
    
    async def do_unew(self, args: str) -> None:
        '''
        UNEW [username] [password] [MODIFIERS]
        Create a new remote user. This does not create a remote session
        '''
        parsed_args: argparse.Namespace = command_parsers.auth_command_parser.parse_args(args.split())
        auth_component: BaseAuthComponent = await op_utils.make_auth_component(username=parsed_args.username, password=parsed_args.password)
        display_credentials, self.end_connection = parsed_args.dc, parsed_args.bye

        await auth_operations.create_remote_user(reader=self.reader, writer=self.writer,
                                                 auth_component=auth_component,
                                                 client_config=self.client_config, session_manager=self.session_master,
                                                 display_credentials=display_credentials, end_connection=self.end_connection)
    
    async def do_udel(self, args: str) -> None:
        '''
        UDEL [username] [password] [MODIFIERS]
        Delete a remote user.
        '''
        parsed_args: argparse.Namespace = command_parsers.auth_command_parser.parse_args(args.split())
        auth_component: BaseAuthComponent = op_utils.make_auth_component(username=parsed_args.username, password=parsed_args.password)
        self.end_connection = parsed_args.bye

        await auth_operations.delete_remote_user(reader=self.reader, writer=self.writer,
                                                 auth_component=auth_component,
                                                 client_config=self.client_config, session_master=self.session_master,
                                                 end_connection=self.end_connection)

        if self.session_master.identity == auth_component.identity:
            self.session_master.clear_auth_data()
        
    @require_auth_state(state=True)
    async def do_sref(self, args: str) -> None:
        '''
        SREF [MODIFIERS]
        Refresh an established remote session
        '''
        parsed_args: argparse.Namespace = command_parsers.generic_modifier_parser.parse_args(args.split())
        display_credentials, self.end_connection = parsed_args.dc, parsed_args.bye
        await auth_operations.end_remote_session(reader=self.reader, writer=self.writer,
                                                 client_config=self.client_config, session_manager=self.session_master,
                                                 display_credentials=display_credentials, end_connection=self.end_connection)

    @require_auth_state(state=True)
    async def do_create(self, args: str) -> None:
        '''
        CREATE [filename] [MODIFIERS]
        Create a new file in the remote directory.
        Filename must include file extension
        '''
        parsed_args: argparse.Namespace = command_parsers.filedir_parser.parse_args(shlex.split(args))
        file_component: BaseFileComponent = BaseFileComponent(subject_file=parsed_args.file, subject_file_owner=parsed_args.directory)
        self.end_connection = parsed_args.bye

        await file_operations.create_file(reader=self.reader, writer=self.writer,
                                          file_component=file_component,
                                          client_config=self.client_config, session_manager=self.session_master,
                                          end_connection=self.end_connection)

    @require_auth_state(state=True)
    async def do_delete(self, args: str) -> None:
        '''
        DELETE [filename] [modifiers]
        Delete a file from a remote directory.
        Filename must include file extension
        '''
        parsed_args: argparse.Namespace = command_parsers.filedir_parser.parse_args(shlex.split(args))
        file_component: BaseFileComponent = BaseFileComponent(subject_file=parsed_args.file, subject_file_owner=parsed_args.directory)
        self.end_connection = parsed_args.bye

        await file_operations.delete_file(reader=self.reader, writer=self.writer,
                                          file_component=file_component,
                                          client_config=self.client_config, session_manager=self.session_master)

    async def do_read(self, args: str) -> None:
        '''
        READ [filename] [directory] [--limit] [--chunk-size] [--pos] [--chunked] [modifiers]
        Read a file from a remote directory.
        '''
        parsed_args: argparse.Namespace = command_parsers.file_command_parser.parse_args(shlex.split(args))
        file_component: BaseFileComponent = BaseFileComponent(subject_file=parsed_args.file, subject_file_owner=parsed_args.directory,
                                                              chunk_size=parsed_args.chunk_size, write_data=None, return_partial=None,
                                                              cursor_position=parsed_args.pos)
        self.end_connection = parsed_args.bye
        await file_operations.read_remote_file(reader=self.reader, writer=self.writer,
                                               file_component=file_component,
                                               client_config=self.client_config, session_manager=self.session_master,
                                               read_limit=parsed_args.limit, chunked_display=parsed_args.chunked)
    
    async def do_write(self, args: str) -> None:
        '''
        WRITE [filename] [directory] [data] [--chunk-size] [--pos] [modifiers]
        Write into a file in a remote directory, overwriting previous contents
        If not specified, remote directory is determined based on remote session
        '''
        parsed_args: argparse.Namespace = command_parsers.file_command_parser.parse_args(shlex.split(args))
        if not parsed_args.write_data:
            raise cmd_errors.CommandException('Missing write data for WRITE operation')
        
        file_component: BaseFileComponent = BaseFileComponent(subject_file=parsed_args.file, subject_file_owner=parsed_args.directory,
                                                              chunk_size=parsed_args.chunk_size, write_data=None,
                                                              cursor_position=parsed_args.pos)
        self.end_connection = parsed_args.bye
        await file_operations.write_remote_file(reader=self.reader, writer=self.writer,
                                                write_data=parsed_args.write_data,
                                                file_component=file_component,
                                                client_config=self.client_config, session_manager=self.session_master)

    @require_auth_state(state=True)
    async def do_append(self, args: str) -> None:
        '''
        APPEND [filename] [directory] [write data] [--chunk-size] [modifiers]
        Append to a file from a remote directory.
        '''
        parsed_args: argparse.Namespace = command_parsers.file_command_parser.parse_args(shlex.split(args))
        if not parsed_args.write_data:
            raise cmd_errors.CommandException('Missing write data for APPEND operation')
        
        file_component: BaseFileComponent = BaseFileComponent(subject_file=parsed_args.file, subject_file_owner=parsed_args.directory,
                                                              chunk_size=parsed_args.chunk_size, write_data=None,
                                                              cursor_position=parsed_args.pos)
        self.end_connection = parsed_args.bye
        await file_operations.append_remote_file(reader=self.reader, writer=self.writer,
                                                 write_data=parsed_args.write_data,
                                                 file_component=file_component,
                                                 chunk_size=parsed_args.chunk_size,
                                                 client_config=self.client_config, session_manager=self.session_master,
                                                 end_connection=parsed_args.bye)
    
    @require_auth_state(state=True)
    async def do_upload(self, arg: str) -> None:
        '''
        UPLOAD [local_fpath] [filename] [--chunk] [modifiers]
        Upload a local file to a remote directory.
        '''

    @require_auth_state(state=True)
    async def do_grant(self, args: str) -> None:
        '''
        GRANT [filename] [directory] [user] [role] [--duration] [modifiers]
        Grant role to user on a given file
        '''
        parsed_args: argparse.Namespace = command_parsers.permission_command_parser.parse_args(shlex.split(args))
        permission_component: BasePermissionComponent = BasePermissionComponent(subject_file=parsed_args.file, subject_file_owner=parsed_args.directory,
                                                                                subject_user=parsed_args.user, effect_duration=parsed_args.duration)
        self.end_connection = parsed_args.bye
        await permission_operations.grant_permission(reader=self.reader, writer=self.writer,
                                                     permission_component=permission_component, role=parsed_args.role,
                                                     client_config=self.client_config, session_manager=self.session_master,
                                                     end_connection=parsed_args.bye)

    @require_auth_state(state=True)
    async def do_revoke(self, args: str) -> None:
        '''
        REVOKE [filename] [directory] [user] [modifiers]
        Revoke a role from a user
        '''
        parsed_args: argparse.Namespace = command_parsers.permission_command_parser.parse_args(shlex.split(args))
        permission_component: BasePermissionComponent = BasePermissionComponent(subject_file=parsed_args.file, subject_file_owner=parsed_args.directory,
                                                                                subject_user=parsed_args.user)
        self.end_connection = parsed_args.bye
        await permission_operations.revoke_permission(reader=self.reader, writer=self.writer,
                                                     permission_component=permission_component,
                                                     client_config=self.client_config, session_manager=self.session_master,
                                                     end_connection=parsed_args.bye)

    @require_auth_state(state=True)
    async def do_transfer(self, args: str) -> None:
        '''
        TRANSFER [filename] [directory] [user] [modifiers]
        Transfer ownership of a file to another user.
        '''
        parsed_args: argparse.Namespace = command_parsers.permission_command_parser.parse_args(shlex.split(args))
        if not parsed_args.user:
            raise ValueError('User needs to be specified')
        permission_component: BasePermissionComponent = BasePermissionComponent(subject_file=parsed_args.file,
                                                                                subject_file_owner=self.session_master.identity,
                                                                                subject_user=parsed_args.user)
        self.end_connection = parsed_args.bye
        await permission_operations.transfer_ownership(reader=self.reader, writer=self.writer,
                                                       permission_component=permission_component,
                                                       client_config=self.client_config, session_manager=self.session_master,
                                                       end_connection=parsed_args.bye)

    @require_auth_state(state=True)
    async def do_publicise(self, args: str) -> None:
        '''
        PUBLISICE [filename] [modifiers]
        Publicise a given file and grant every remote user read access, without overriding any previosuly granted permissions.
        This operation can only be performed on the files in the user's own directory
        '''
        parsed_args: argparse.Namespace = command_parsers.filedir_parser.parse_args(shlex.split(args))
        permission_component: BasePermissionComponent = BasePermissionComponent(subject_file=parsed_args.file, subject_file_owner=self.session_master.identity)
        self.end_connection = parsed_args.bye
        await permission_operations.publicise_remote_file(reader=self.reader, writer=self.writer,
                                                          permission_component=permission_component,
                                                          client_config=self.client_config, session_manager=self.session_master,
                                                          end_connection=parsed_args.bye)

    @require_auth_state(state=True)
    async def do_hide(self, args: str) -> None:
        '''
        HIDE [filename] [directory] [modifiers]
        '''
        parsed_args: argparse.Namespace = command_parsers.filedir_parser.parse_args(shlex.split(args))
        permission_component: BasePermissionComponent = BasePermissionComponent(subject_file=parsed_args.file, subject_file_owner=self.session_master.identity)
        self.end_connection = parsed_args.bye
        await permission_operations.hide_remote_file(reader=self.reader, writer=self.writer,
                                                     permission_component=permission_component,
                                                     client_config=self.client_config, session_manager=self.session_master,
                                                     end_connection=parsed_args.bye)

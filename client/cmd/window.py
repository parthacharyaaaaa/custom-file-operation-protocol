import asyncio
import cmd
import functools
import inspect
from typing import Optional, Callable, Any

from client import session_manager
from client.cmd import parsers, cmd_utils
from client.cmd.commands import GeneralModifierCommands, FileCommands
from client.cmd import errors as cmd_errors 
from client.config import constants as client_constants
from client.operations import auth_operations, file_operations, permission_operations, info_operations

from models.request_model import BaseAuthComponent, BaseFileComponent, BasePermissionComponent

class ClientWindow(cmd.Cmd):
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

        self.prompt = f'{host}:{port}>'
        super().__init__(completekey, stdin, stdout)

    def parseline(self, line: str):
        cmd, arg, line = super().parseline(line.upper())
        return cmd.lower(), arg, line

    def default(self, line):
        self.stdout.write(f'UNKNOWN COMMAND: {line.split()[0]}\n')
        self.do_help(None)

    async def postcmd(self, stop, line):
        if self.connection_ended:
            self.writer.close()
            await self.writer.wait_closed()

            if self.session_master.identity:
                self.session_master.clear_auth_data()
            
            return True

    async def cmdloop(self, intro = None):
        self.preloop()
        if self.use_rawinput and self.completekey:
            try:
                import readline
                self.old_completer = readline.get_completer()
                readline.set_completer(self.complete)
                readline.parse_and_bind(self.completekey+": complete")
            except ImportError:
                pass
        try:
            if intro is not None:
                self.intro = intro
            if self.intro:
                self.stdout.write(str(self.intro)+"\n")
            stop = None
            while not stop:
                if self.cmdqueue:
                    line = self.cmdqueue.pop(0)
                else:
                    if self.use_rawinput:
                        try:
                            line = input(self.prompt)
                        except EOFError:
                            line = 'EOF'
                    else:
                        self.stdout.write(self.prompt)
                        self.stdout.flush()
                        line = self.stdin.readline()
                        if not len(line):
                            line = 'EOF'
                        else:
                            line = line.rstrip('\r\n')
                line = self.precmd(line)
                stop = await self.onecmd(line)
                stop = await self.postcmd(stop, line)
            self.postloop()
        finally:
            if self.use_rawinput and self.completekey:
                try:
                    import readline
                    readline.set_completer(self.old_completer)
                except ImportError:
                    pass

    async def onecmd(self, line):
        cmd, arg, line = self.parseline(line)
        if not line:
            return self.emptyline()
        if cmd is None:
            return self.default(line)
        self.lastcmd = line
        if line == 'EOF' :
            self.lastcmd = ''
        if cmd == '':
            return self.default(line)
        else:
            try:
                func = getattr(self, 'do_' + cmd)
            except AttributeError:
                return self.default(line)
            
            # Additional logic added here to deal with any asynchronous functions
            try:
                if inspect.iscoroutinefunction(inspect.unwrap(func)):
                    return await func(arg)
                else:
                    return func(arg)
            except cmd_errors.CommandException as cmd_exc:
                await cmd_utils.display(cmd_exc.description)
            
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
    async def do_heartbeat(self, arg: str) -> None:
        '''
        HEARTBEAT [modifiers]
        Send a heartbeat signal to the connected process
        '''
        tokens: list[str] = arg.split()
        self.end_connection = await parsers.parse_modifiers(tokens, GeneralModifierCommands.END_CONNECTION)
        await info_operations.send_heartbeat(self.reader, self.writer, self.client_config, self.session_master, self.end_connection)

    @require_auth_state(state=False)
    async def do_auth(self, arg: str) -> None:
        '''
        AUTH [username] [password] [MODIFIERS]
        Start a remote session on the host machine.
        This is the recommended way of starting a remote session, as it avoids writing password to shell history'''
        tokens: list[str] = arg.split()
        auth_component: BaseAuthComponent = parsers.parse_authorization(tokens)
        display_credentials, self.end_connection = parsers.parse_modifiers(tokens)
        
        await auth_operations.authorize(self.reader, self.writer, auth_component, self.client_config, self.session_master, display_credentials, self.end_connection)

    @require_auth_state(state=True)
    async def do_sterm(self, arg: str) -> None:
        '''
        STERM [MODIFIERS]
        Terminate an established remote session
        '''
        tokens: list[str] = arg.split()
        display_credentials, self.end_connection = parsers.parse_auth_modifiers(tokens)
        await auth_operations.end_remote_session(self.reader, self.writer, self.client_config, self.session_master, display_credentials, self.end_connection)
    
    async def do_unew(self, arg: str) -> None:
        '''
        UNEW [username] [password] [MODIFIERS]
        Create a new remote user. This does not create a remote session
        '''
        tokens: list[str] = arg.split()
        auth_component: BaseAuthComponent = parsers.parse_authorization(tokens)
        display_credentials, self.end_connection = parsers.parse_auth_modifiers(tokens)

        await auth_operations.create_remote_user(self.reader, self.writer, auth_component, self.client_config, display_credentials, self.end_connection)
    
    async def do_udel(self, arg: str) -> None:
        '''
        UDEL [username] [password] [MODIFIERS]
        Delete a remote user.
        '''
        tokens: list[str] = arg.split()

        auth_component: BaseAuthComponent = parsers.parse_authorization(tokens)
        display_credentials, self.end_connection = parsers.parse_auth_modifiers(tokens)

        await auth_operations.delete_remote_user(self.reader, self.writer, auth_component, self.client_config, self.session_master, display_credentials, self.end_connection)

        if self.session_master.identity == auth_component.identity:
            self.session_master.clear_auth_data()
        

    @require_auth_state(state=True)
    async def do_sref(self, arg: str) -> None:
        '''
        SREF [MODIFIERS]
        Refresh an established remote session
        '''
        tokens: list[str] = arg.split()
        display_credentials, self.end_connection = parsers.parse_auth_modifiers(tokens)
        await auth_operations.end_remote_session(self.reader, self.writer, self.client_config, self.session_master, display_credentials, self.end_connection)


    @require_auth_state(state=True)
    async def do_create(self, arg: str) -> None:
        '''
        CREATE [filename] [MODIFIERS]
        Create a new file in the remote directory.
        Filename must include file extension
        '''
        tokens: list[str] = arg.split()
        file_component: BaseFileComponent = parsers.parse_file_command(tokens, FileCommands.CREATE, self.session_master.identity, False)
        file_component.cursor_keepalive, self.end_connection = parsers.parse_modifiers(tokens, GeneralModifierCommands.CURSOR_KEEPALIVE, GeneralModifierCommands.END_CONNECTION)

        await file_operations.create_file(self.reader, self.writer,
                                          file_component, self.client_config, self.session_master, self.end_connection)

    @require_auth_state(state=True)
    async def do_delete(self, arg: str) -> None:
        '''
        DELETE [filename]
        Delete a file from a remote directory.
        Filename must include file extension
        '''
        tokens: list[str] = arg.split()
        file_component: BaseFileComponent = parsers.parse_file_command(tokens, FileCommands.DELETE, self.session_master.identity, False)
        file_component.cursor_keepalive = False

        self.end_connection = parsers.parse_modifiers(tokens, GeneralModifierCommands.END_CONNECTION)
        await file_operations.delete_file(self.reader, self.writer, file_component, self.client_config, self.session_master)

    def do_read(self, filename: str, directory: Optional[str] = None) -> None:
        '''
        READ [filename] [directory]
        Read a file from a remote directory.
        If not specified, remote directory is determined based on remote session
        '''
        ...
    
    def do_write(self, filename: str, directory: Optional[str] = None) -> None:
        '''
        WRITE [filename] [directory]
        Write into a file in a remote directory, overwriting previous contents
        If not specified, remote directory is determined based on remote session
        '''
        ...
    
    def do_append(self, filename: str, directory: Optional[str] = None) -> None:
        '''
        APPEND [filename] [directory]
        Append to a file from a remote directory.
        If not specified, remote directory is determined based on remote session
        '''
        ...
    
    @require_auth_state(state=True)
    async def do_upload(self, arg: str) -> None:
        '''
        UPLOAD [local_fpath] [optional: remote filename] [modifiers]
        Upload a local file to a remote directory.
        '''
        tokens: list[str] = arg.split()
        local_fpath: str = tokens[0]
        remote_fname: str = None
        
        if len(tokens) > 1 and tokens[1] not in GeneralModifierCommands._value2member_map_:
            remote_fname = tokens[1]
         
        cursor_keepalive, end_connection = parsers.parse_modifiers(tokens[1:], GeneralModifierCommands.CURSOR_KEEPALIVE, GeneralModifierCommands.END_CONNECTION)
        
        await file_operations.upload_remote_file(self.reader, self.writer, local_fpath, self.client_config, self.session_master, remote_fname, None, end_connection, cursor_keepalive)

    @require_auth_state(state=True)
    async def do_grant(self, arg: str) -> None:
        '''
        GRANT [filename] [directory] [user] [role] [optional: duration] [modifiers]
        Grant role to user on a given file
        '''
        tokens: list[str] = arg.split()
        permission_component, subcategory_bits = parsers.parse_grant_command(tokens)
        self.end_connection = parsers.parse_modifiers(tokens, GeneralModifierCommands.END_CONNECTION)

        await permission_operations.grant_permission(self.reader, self.writer, subcategory_bits, permission_component, self.client_config, self.session_master)
    
    @require_auth_state(state=True)
    async def do_revoke(self, arg: str) -> None:
        '''
        REVOKE [filename] [directory] [user] [modifiers]
        Revoke a role from a user
        '''
        tokens: list[str] = arg.split()
        permission_component: BasePermissionComponent = parsers.parse_generic_permission_command(tokens)
        self.end_connection = parsers.parse_modifiers(tokens[3:], GeneralModifierCommands.END_CONNECTION)

        await permission_operations.revoke_permission(self.reader, self.writer, permission_component, self.client_config, self.session_master, self.end_connection)

    @require_auth_state(state=True)
    async def do_transfer(self, arg: str) -> None:
        '''
        TRANSFER [filename] [directory] [user] [modifiers]
        Transfer ownership of a file to another user.
        '''
        tokens: list[str] = arg.split()
        permission_component: BasePermissionComponent = parsers.parse_generic_permission_command(tokens[:3])
        self.end_connection = parsers.parse_modifiers(tokens[3:])

        await permission_operations.transfer_ownership(self.reader, self.writer, permission_component, self.client_config, self.session_master, self.end_connection)

    @require_auth_state(state=True)
    async def do_publicise(self, arg: str) -> None:
        '''
        PUBLISICE [filename] [directory] [modifiers]
        Publicise a given file and grant every remote user read access, without overriding any previosuly granted permissions
        '''
        tokens: list[str] = arg.split()
        permission_component: BasePermissionComponent = parsers.parse_generic_permission_command(tokens, include_user=False)
        self.end_connection = parsers.parse_modifiers(tokens)

        await permission_operations.publicise_remote_file(self.reader, self.writer, permission_component, self.client_config, self.session_master, self.end_connection)
    
    @require_auth_state(state=True)
    async def do_hide(self, arg: str) -> None:
        '''
        HIDE [filename] [directory] [modifiers]
        '''
        tokens: list[str] = arg.split()
        permission_component: BasePermissionComponent = parsers.parse_generic_permission_command(tokens, include_user=False)
        self.end_connection = parsers.parse_modifiers(tokens)

        await permission_operations.hide_remote_file(self.reader, self.writer, permission_component, self.client_config, self.session_master, self.end_connection)
    

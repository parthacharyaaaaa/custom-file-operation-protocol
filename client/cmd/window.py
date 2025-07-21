import asyncio
import cmd
import os
from typing import Optional

from client import session_manager
from client.cmd import parsers
from client.cmd.commands import GeneralModifierCommands
from client.config import constants as client_constants
from client.operations import auth_operations


from models.request_model import BaseAuthComponent

class ClientWindow(cmd):
    
    # Overrides
    def __init__(self, host: str, port: int,
                 reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 client_config: client_constants.ClientConfig, session_master: session_manager.SessionManager,
                 completekey = "tab", stdin = None, stdout = None):
        
        self.reader: asyncio.StreamReader = reader
        self.writer: asyncio.StreamWriter = writer
        self.client_config: client_constants.ClientConfig = client_config
        self.session_master: session_manager.SessionManager = session_master

        self.prompt = f'{host}:{port}>'
        super().__init__(completekey, stdin, stdout)

    def parseline(self, line: str):
        cmd, arg, line = super().parseline(line.upper())
        return cmd.lower(), arg, line

    def default(self, line):
        self.stdout.write(f'UNKNOWN COMMAND: {line.split()[0]}\n')
        self.do_help(None)

    # Methods
    def do_heartbeat(self) -> None:
        '''
        HEARTBEAT
        Send a heartbeat signal to the connected process
        '''

    async def do_auth(self, arg: str) -> None:
        '''
        AUTH [username] [password] [end_connection]
        Start a remote session on the host machine.
        This is the recommended way of starting a remote session, as it avoids writing password to shell history'''
        tokens: list[str] = arg.split()
        auth_component: BaseAuthComponent = parsers.parse_authorization(tokens)
        display_credentials, end_connection = parsers.parse_modifiers(tokens[2:],
                                                                      GeneralModifierCommands.DISPLAY_CREDENTIALS.value,
                                                                      GeneralModifierCommands.END_CONNECTION.value)
        
        await auth_operations.authorize(self.reader, self.writer, auth_component, self.client_config, self.session_master, display_credentials, end_connection)

    def do_sterm(self) -> None:
        '''
        STERM
        Terminate an established remote session
        '''
        ...
    
    def do_sref(self) -> None:
        '''
        SREF
        Refresh an established remote session
        '''
        ...


    def do_create(self, filename: str) -> None:
        '''
        CREATE [filename]
        Create a new file in the remote directory.
        Filename must include file extension
        '''
        ...

    def do_delete(self, filename: str, directory: Optional[str] = None) -> None:
        '''
        DELETE [filename] [directory]
        Delete a file from a remote directory.
        If not specified, remote directory is determined based on remote session
        '''
        ...

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
    
    def do_upload(self, local_fpath: os.PathLike) -> None:
        '''
        UPLOAD [local_fpath]
        Upload a local file to a remote directory.
        '''
        ...


    
ClientWindow('localhost', 5000).cmdloop()
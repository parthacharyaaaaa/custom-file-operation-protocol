import asyncio
import os
from typing import Any
import pytomlpp

from client.config.constants import ClientConfig
from client.cmd.window import ClientWindow
from client.session_manager import SessionManager
from client.communication import incoming, outgoing

from models.response_codes import SuccessFlags

__all__ = ('init_session_manager', 'init_client_configurations', 'init_cmd_window', 'create_server_connection')

def init_session_manager() -> SessionManager:
    return SessionManager()

def init_client_configurations() -> ClientConfig:
    constants_mapping: dict[str, Any] = pytomlpp.load(os.path.join(os.path.dirname(__file__), 'config', 'constants.toml'))
    client_config = ClientConfig.model_validate(constants_mapping)

    return client_config

def init_cmd_window(host: str, port: int,
                    reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                    client_config: ClientConfig, session_manager: SessionManager) -> ClientWindow:
    return ClientWindow(host, port, reader, writer, client_config, session_manager)

async def create_server_connection(host: str, port: int, timeout: float) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    #TODO: Add SSL
    return await asyncio.open_connection(host, port)

async def heartbeat_monitor(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_manager: SessionManager, hb_interval: float, read_timeout: float = 3.0) -> None:
    '''Background task for monitoring heartbeat of the remote server'''
    conn_teardown: bool = False
    while True:
        await outgoing.send_request(writer, reader)
        try:
            heartbeat_header, _ = await incoming.process_response(reader, writer, read_timeout)
            if heartbeat_header.code != SuccessFlags.HEARTBEAT.value:
                conn_teardown = True
        except asyncio.TimeoutError:
            conn_teardown = True
        
        if conn_teardown:
            async with outgoing.STREAM_LOCK:
                writer.close()
                await writer.wait_closed()

            session_manager.clear_auth_data()
            asyncio.get_event_loop().call_exception_handler({
                'exception' : TimeoutError('Server heartbeat stopped'),
                'task' : asyncio.current_task(),
                'message' : 'Server timeout'
            })
            return
        
        await asyncio.sleep(hb_interval)
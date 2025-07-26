import asyncio
import os
from typing import Any
import pytomlpp

from client.config.constants import ClientConfig
from client.cmd.window import ClientWindow
from client.session_manager import SessionManager

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
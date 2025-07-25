import os
from typing import Any
import pytomlpp

from client.config.constants import ClientConfig
from client.session_manager import SessionManager

__all__ = ('init_session_manager', 'init_client_configurations',)

def init_session_manager() -> SessionManager:
    return SessionManager()

def init_client_configurations() -> ClientConfig:
    constants_mapping: dict[str, Any] = pytomlpp.load(os.path.join(os.path.dirname(__file__), 'config', 'constants.toml'))
    client_config = ClientConfig.model_validate(constants_mapping)

    return client_config
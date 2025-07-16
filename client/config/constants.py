import os
from typing import Annotated, Any

from pydantic import BaseModel, Field
import pytomlpp

from models.constants import REQUEST_CONSTANTS

__all__ = ('ClientConfig', 'CLIENT_CONFIG',)

class ClientConfig(BaseModel):
    version: Annotated[str, Field(frozen=True, pattern=REQUEST_CONSTANTS.header.version_regex)]
    read_timeout: Annotated[float, Field(frozen=True, ge=0)]

CLIENT_CONFIG: ClientConfig = None

def initialize_client_configurations() -> ClientConfig:
    global CLIENT_CONFIG
    constants_mapping: dict[str, Any] = pytomlpp.load(os.path.join(os.path.dirname(__file__), 'constants.toml'))
    CLIENT_CONFIG = ClientConfig.model_validate(constants_mapping)

    return CLIENT_CONFIG
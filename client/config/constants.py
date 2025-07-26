from typing import Annotated
from pydantic import BaseModel, Field
from models.constants import REQUEST_CONSTANTS

__all__ = ('ClientConfig',)

class ClientConfig(BaseModel):
    version: Annotated[str, Field(frozen=True, pattern=REQUEST_CONSTANTS.header.version_regex)]
    read_timeout: Annotated[float, Field(frozen=True, ge=0)]
    ssl_handshake_timeout: Annotated[float, Field(frozen=True, ge=0)]
    heartbeat_interval: Annotated[float, Field(ge=0)]

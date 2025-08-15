from typing import Annotated, Union
from pydantic import BaseModel, Field, field_validator
from models.constants import REQUEST_CONSTANTS

from pathlib import Path

__all__ = ('ClientConfig',)

class ClientConfig(BaseModel):
    version: Annotated[str, Field(frozen=True, pattern=REQUEST_CONSTANTS.header.version_regex)]
    read_timeout: Annotated[float, Field(frozen=True, ge=0)]
    ssl_handshake_timeout: Annotated[float, Field(frozen=True, ge=0)]
    heartbeat_interval: Annotated[float, Field(ge=0)]
    server_fingerprints_filepath: Path
    ciphers: Annotated[str, Field(frozen=True)]

    @field_validator('server_fingerprints_filepath', mode='before')
    @classmethod
    def process_fingerprints_filename(cls, path: Union[str, Path]) -> Path:
        return Path(path) if isinstance(path, str) else path
    
    @field_validator('ciphers', mode='before')
    @classmethod
    def prevaldiate_ciphers(cls, ciphers: str) -> str:
        return ciphers.strip().upper()

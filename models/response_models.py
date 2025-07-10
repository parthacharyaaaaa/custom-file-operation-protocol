'''Module for defining schema of outgoing responses'''
from time import time
from typing import Annotated, Optional, Any

from server.errors import ProtocolException

from models.constants import REQUEST_CONSTANTS, RESPONSE_CONSTANTS
from models.response_codes import CODES
from server.config.server_config import ServerConfig

from pydantic import BaseModel, IPvAnyAddress, Field

class ResponseHeader(BaseModel):
    # Protocol metadata
    version: Annotated[str, Field(min_length=5, max_length=12, pattern=REQUEST_CONSTANTS.header.version_regex)]
    
    # Response metadata
    code: Annotated[str, Field(min_length=3, pattern=RESPONSE_CONSTANTS.header.code_regex)]
    description: Annotated[Optional[str], Field(max_length=RESPONSE_CONSTANTS.header.description_max_length, default=None)]

    # Responder metadata
    responder_hostname: Annotated[IPvAnyAddress, Field(frozen=True)]
    responder_port: Annotated[int, Field(frozen=True)]
    responder_timestamp: Annotated[float, Field(default_factory=time)]

    # Response contents
    body_size: Annotated[int, Field(default=0)]
    
    # Connection status
    ended_connection: Annotated[bool, Field(default=False)]

    # Additonal key-value pairs
    kwargs: Optional[
        Annotated[
            dict[
                Annotated[str, Field(min_length=RESPONSE_CONSTANTS.header.kwarg_key_range[0], max_length=RESPONSE_CONSTANTS.header.kwarg_key_range[1])],
                Annotated[str, Field(min_length=RESPONSE_CONSTANTS.header.kwarg_value_range[0], max_length=RESPONSE_CONSTANTS.header.kwarg_value_range[1])]
                ],
            Field(default=None)
        ]
    ] = None

    def validate_code(self) -> bool:
        for response_category in CODES:
            if self.code in response_category:
                return True
        return False
    
    @classmethod
    def from_server(cls, config: ServerConfig, code: int, version: Optional[str] = None, description: Optional[str] = None, responder_timestamp: Optional[float] = None, body_size: int = 0, ended_connection: bool = False, **kwargs) -> 'ResponseHeader':
        return cls(version=version or config.version, code=code, description=description,
                   responder_timestamp = responder_timestamp or time(), responder_hostname=config.host, responder_port=config.port,
                   body_size=body_size,
                   ended_connection=ended_connection, kwargs=kwargs)

    @classmethod
    def make_response_header(cls, version: Optional[str], code: int, description: str, host: str, port: int, responder_timestamp: Optional[float] = None, body_size: int = 0, end_conn: bool = False, **kwargs) -> 'ResponseHeader':
        return cls(version=version,
                   code=code, description=description,
                   responder_hostname=host, responder_port=port, responder_timestamp=responder_timestamp or time(),
                   body_size=body_size, ended_connection=end_conn,
                   kwargs=kwargs)
    
    @classmethod
    def from_protocol_exception(cls, exc: type[ProtocolException], version: str, host: str, port: int, responder_timestamp: Optional[float] = None, end_conn: bool = False, **kwargs) -> 'ResponseHeader':
        return cls(version=version,
                   code=exc.code,
                   description=exc.description,
                   responder_hostname=host, responder_port=port, responder_timestamp=responder_timestamp or time(),
                   body_size=0,
                   end_connection=end_conn,
                   kwargs=kwargs)
    
    @classmethod
    def from_unverifiable_data(cls, exc: type[ProtocolException], version: str, host: str, port: int, responder_timestamp: Optional[float] = None, end_conn: bool = False, **kwargs) -> 'ResponseHeader':
        return cls(version=version,
                   code=exc.code,
                   description=exc.description,
                   responder_hostname=host, responder_port=port, responder_timestamp=responder_timestamp or time(),
                   body_size=0,
                   end_connection=end_conn,
                   **kwargs)
    
    
    def as_bytes(self) -> bytes:
        return self.model_dump_json().encode('utf-8')

class ResponseBody(BaseModel):
    contents: dict[str, Any]

    chunk_number: Annotated[Optional[int], Field(ge=0, frozen=True, default=None)]
    return_partial: Annotated[Optional[bool], Field(default=True)]
    cursor_position: Annotated[Optional[int], Field(le=0, default=0, frozen=True)]
    cursor_keepalive_accepted: Annotated[bool, Field(default=False)]
    
    
    def as_bytes(self) -> bytes:
        return self.model_dump_json().encode('utf-8')
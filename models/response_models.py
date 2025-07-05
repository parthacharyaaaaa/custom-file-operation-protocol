'''Module for defining schema of outgoing responses'''
from pydantic import BaseModel, IPvAnyAddress, Field
from typing import Annotated, Optional, Union
from response_codes import CODES
from server.config import ServerConfig
from models.request_model import BaseHeaderComponent
from datetime import datetime
from time import time
from server.errors import ProtocolException

class ResponseHeader(BaseModel):
    # Protocol metadata
    version: Annotated[str, Field(min_length=5, max_length=12, pattern=ServerConfig.VERSION_REGEX.value)]
    
    # Response metadata
    code: Annotated[str, Field(min_length=3, pattern=ServerConfig.RESPONSE_CODE_REGEX.value)]
    description: Optional[Annotated[str, Field(max_length=256, default=None)]]

    # Responder metadata
    responder_hostname: Annotated[IPvAnyAddress, Field(frozen=True, default=ServerConfig.HOST.value)]
    responder_port: Annotated[int, Field(frozen=True, default=ServerConfig.PORT.value)]
    responder_timestamp: Annotated[float, Field(frozen=True, default_factory=datetime.now)]

    # Response contents
    body_size: Annotated[int, Field(frozen=True, default=0)]
    
    # Connection status
    ended_connection: Annotated[bool, Field(default=False)]

    # Additonal key-value pairs
    kwargs: Optional[
        Annotated[
            dict[
                Annotated[str, Field(min_length=4, max_length=16)],
                Annotated[str, Field(min_length=1, max_length=128)]
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
    def make_response_header(cls, version: Optional[str], code: int, description: str, hostname: Optional[str] = None, port: Optional[int] = None, responder_timestamp: Optional[float] = None, body_size: int = 0, end_conn: bool = False, **kwargs) -> 'ResponseHeader':
        return cls(version=version or ServerConfig.VERSION.value,
                   code=code, description=description,
                   responder_hostname=hostname or ServerConfig.HOST.value, responder_port=port or ServerConfig.PORT.value, responder_timestamp=responder_timestamp or time(),
                   body_size=body_size, ended_connection=end_conn,
                   kwargs=kwargs)
    
    @classmethod
    def from_protocol_exception(cls, exc: type[ProtocolException], context_request: BaseHeaderComponent, hostname: Optional[str] = None, port: Optional[int] = None, responder_timestamp: Optional[float] = None, end_conn: bool = False, **kwargs) -> 'ResponseHeader':
        return cls(version=context_request.version,
                   code=exc.code,
                   description=exc.description,
                   responder_hostname=hostname or ServerConfig.HOST.value, responder_port=port or ServerConfig.PORT.value, responder_timestamp=responder_timestamp or time(),
                   body_size=0,
                   end_connection=end_conn,
                   kwargs=kwargs)
    
    @classmethod
    def from_unverifiable_data(cls, exc: type[ProtocolException], version: Optional[int] = None,hostname: Optional[str] = None, port: Optional[int] = None, responder_timestamp: Optional[float] = None, end_conn: Optional[bool] = False, **kwargs) -> 'ResponseHeader':
        return cls(version=version or ServerConfig.VERSION.value,
                   code=exc.code,
                   description=exc.description,
                   responder_hostname=hostname or ServerConfig.HOST.value, responder_port=port or ServerConfig.PORT.value, responder_timestamp=responder_timestamp or time(),
                   body_size=0,
                   end_connection=end_conn,
                   **kwargs)

class ResponseBody(BaseModel):
    contents: Union[bytes, str]
    chunk_number: Optional[Annotated[int, Field(ge=0, frozen=True, default=None)]]
    return_partial: Optional[Annotated[bool, Field(default=True)]]\
    
    keepalive_accepted: Optional[bool]
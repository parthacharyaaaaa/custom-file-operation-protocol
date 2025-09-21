'''Module for defining schema of outgoing responses'''
from ipaddress import IPv4Address, IPv6Address
from time import time
from typing import Optional, Any, Union, TYPE_CHECKING
from typing_extensions import Self

from models.constants import REQUEST_CONSTANTS
from models.typing import ResponseCode
from models.response_codes import ClientErrorFlags, ServerErrorFlags

from pydantic import BaseModel, Field
from pydantic.networks import IPvAnyAddress

from server.config.server_config import ServerConfig
from server.errors import ProtocolException

__all__ = ('ResponseHeader',
           'ResponseBody')

if TYPE_CHECKING: assert REQUEST_CONSTANTS

def _cast_as_ip_address(ip_address: str) -> IPvAnyAddress:
    return IPv6Address(ip_address) if ':' in ip_address else IPv4Address(ip_address)

def _cast_as_response_code(code: str) -> Union[ClientErrorFlags, ServerErrorFlags]:
    if code in (flag.value for flag in ClientErrorFlags):
        return ClientErrorFlags(code)
    return ServerErrorFlags(code)

class ResponseHeader(BaseModel):
    # Protocol metadata
    version: str = Field(min_length=5, max_length=12, pattern=REQUEST_CONSTANTS.header.version_regex)
    
    # Response metadata
    code: ResponseCode = Field(frozen=True)

    # Responder metadata
    responder_hostname: IPvAnyAddress = Field(frozen=True)
    responder_port: int = Field(frozen=True)
    responder_timestamp: float = Field(default_factory=time)

    # Response contents
    body_size: int = Field(default=0)
    
    # Connection status
    ended_connection: bool = Field(default=False)
    
    @classmethod
    def from_server(cls,
                    config: ServerConfig,
                    code: ResponseCode,
                    version: Optional[str] = None,
                    responder_timestamp: Optional[float] = None,
                    body_size: int = 0,
                    ended_connection: bool = False) -> Self:
        return cls(version=version or config.version,
                   code=code,
                   responder_timestamp = responder_timestamp or time(),
                   responder_hostname=config.host,
                   responder_port=config.port,
                   body_size=body_size,
                   ended_connection=ended_connection)

    @classmethod
    def make_response_header(cls,
                             version: str,
                             code: ResponseCode,
                             host: str, port: int,
                             responder_timestamp: Optional[float] = None,
                             body_size: int = 0,
                             end_conn: bool = False) -> 'ResponseHeader':
        return cls(version=version,
                   code=code,
                   responder_hostname=_cast_as_ip_address(host),
                   responder_port=port,
                   responder_timestamp=responder_timestamp or time(),
                   body_size=body_size, ended_connection=end_conn)
    
    @classmethod
    def from_protocol_exception(cls,
                                exc: type[ProtocolException],
                                version: str,
                                host: str, port: int,
                                responder_timestamp: Optional[float] = None,
                                end_conn: bool = False) -> 'ResponseHeader':
        return cls(version=version,
                   code=_cast_as_response_code(exc.code),
                   responder_hostname=_cast_as_ip_address(host),
                   responder_port=port,
                   responder_timestamp=responder_timestamp or time(),
                   body_size=0,
                   ended_connection=end_conn)
    
    @classmethod
    def from_unverifiable_data(cls,
                               exc: type[ProtocolException],
                               version: str,
                               host: str, port: int,
                               responder_timestamp: Optional[float] = None,
                               end_conn: bool = False) -> 'ResponseHeader':
        return cls(version=version,
                   code=_cast_as_response_code(exc.code),
                   responder_hostname=_cast_as_ip_address(host),
                   responder_port=port,
                   responder_timestamp=responder_timestamp or time(),
                   body_size=0,
                   ended_connection=end_conn)
    
    
    def as_bytes(self) -> bytes:
        return self.model_dump_json().encode('utf-8')

class ResponseBody(BaseModel):
    contents: Optional[dict[str, Any]] = Field(default=None)

    operation_ended: Optional[bool] = Field(default=True)
    cursor_position: Optional[int] =  Field(ge=0, default=0, frozen=True)
    cursor_keepalive_accepted: bool = Field(default=False)
    
    def as_bytes(self) -> bytes:
        return self.model_dump_json().encode('utf-8')
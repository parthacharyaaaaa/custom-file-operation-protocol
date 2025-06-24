'''Module for defining schema of outgoing responses'''
from pydantic import BaseModel, IPvAnyAddress, model_validator, Field
from typing import Annotated, Optional, Union, Any
from server import response_codes
from server.config import ServerConfig
from server.models.request_model import BaseHeaderComponent
from datetime import datetime
from server.errors import ProtocolException

class ResponseHeader(BaseModel):
    version: Annotated[int, Field(ge=0)]
    code: str
    sender_address: Annotated[IPvAnyAddress, Field(frozen=True)]
    sequence_number: Annotated[int, Field(frozen=True, ge=0)]
    sender_timestamp: datetime
    body_size: Annotated[int, Field(frozen=True, default=0)]
    description: Annotated[str, Field(max_length=64)]
    end_connection: Annotated[bool, Field(default=False)]
    kwargs: Optional[dict[Annotated[str, Field(min_length=4, max_length=16)], Annotated[str, Field(min_length=1, max_length=128)]]]

    def validate_code(self) -> bool:
        for response_category in response_codes:
            if self.code in response_category:
                return True
        return False
    
    @classmethod
    def from_protocol_exception(cls, exc: type[ProtocolException], context_request: BaseHeaderComponent, end_conn: bool = False, body_size: Optional[int] = None, sequence_number: Optional[int] = None, **kwargs) -> 'ResponseHeader':
        return cls(version=context_request.version,
                   code=exc.code,
                   sender_address=f'{ServerConfig.HOST}:{ServerConfig.PORT}',
                   sequence_number=sequence_number or context_request.sequence_number+1,
                   sender_timestamp=datetime.now(),
                   body_size=body_size or 0,
                   description=exc.description,
                   end_connection=end_conn,
                   kwargs=kwargs)
    
    @classmethod
    def from_unverifiable_data(cls, exc: type[ProtocolException], version: Optional[int] = None, seq_num: Optional[int] = None, end_conn: Optional[bool] = False, **kwargs) -> 'ResponseHeader':
        return cls(version=version or ServerConfig.VERSION,
                   code=exc.code,
                   description=exc.description,
                   sender_address=f'{ServerConfig.HOST}:{ServerConfig.PORT}',
                   sequence_number=seq_num or 0,
                   sender_timestamp=datetime.now(),
                   body_size=0,
                   end_connection=end_conn,
                   kwargs=kwargs)

class ResponseBody(BaseModel):
    data: Union[bytes, str]
    partial: bool = False
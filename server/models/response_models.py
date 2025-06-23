'''Module for defining schema of outgoing responses'''
from pydantic import BaseModel, IPvAnyAddress, model_validator, Field
from typing import Annotated, Optional, Union
from server import response_codes
from datetime import datetime

class ResponseHeader(BaseModel):
    version: Annotated[int, Field(ge=0)]
    code: str
    sender_address: Annotated[IPvAnyAddress, Field(frozen=True)]
    sequence_number: Annotated[int, Field(frozen=True, ge=1)]
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

class ResponseBody(BaseModel):
    data: Union[bytes, str]
    partial: bool = False
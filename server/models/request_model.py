'''Module for defining schema of incoming requests'''
from pydantic import BaseModel, Field, model_validator, IPvAnyAddress
from typing import Annotated, Optional, Literal
from datetime import datetime
from server.config import CategoryFlag

class BaseAuthComponent(BaseModel):
    identity: Annotated[str, Field(min_length=8, max_length=64)]
    password: Optional[Annotated[str, Field(min_length=16, max_length=1024)]]
    token: Optional[Annotated[str, Field(min_length=16, max_length=1024)]]
    max_time: Annotated[int, Field(ge=16, le=86400)]

    @model_validator(mode='after')
    def auth_semantic_check(self) -> 'BaseAuthComponent':
        if not (self.password or self.token):
            raise ValueError('Passkey or token required for authentication')
        return self
    
class BaseFileComponent(BaseModel):
    subject_file: str
    read_range: Optional[Annotated[int, Field(ge=0, le=4096, frozen=True, default=None)]]
    write_buffer: Optional[Annotated[str, Field(min_length=1, max_length=4096, frozen=True, default=None)]]
    return_partial: Optional[Annotated[bool, Field(default=True)]]

    @model_validator(mode='after')
    def file_op_semantic_check(self) -> 'BaseFileComponent':
        if not (self.read_range or self.write_buffer):
            raise Exception('Missing any operational data')
        return self

class BasePermissionComponent(BaseModel):
    subject_file: Annotated[str, Field(frozen=True)]
    subject_user: Optional[str]
    effect_duration: Optional[Annotated[int, Field(le=0, ge=2_678_400, frozen=True, default=0)]]
    
class BaseHeaderComponent(BaseModel):
    version: Annotated[int, Field(ge=0)]
    auth_size: Annotated[int, Field(frozen=True)]
    body_size: Annotated[int, Field(frozen=True)]
    sender_address: Annotated[IPvAnyAddress, Field(frozen=True)]
    sequence_number: Annotated[int, Field(frozen=True, ge=1)]
    sender_timestamp: datetime
    finish: bool = False
    category: Annotated[CategoryFlag, Field(frozen=True)]    # 0b0001, 0b0010, 0b0100, and 0b1000
    subcategory: Annotated[int, Field(frozen=True, ge=1)]   # Also bitmask literals, but depending on parent category the values can differ
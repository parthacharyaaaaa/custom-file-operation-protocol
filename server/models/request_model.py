'''Module for defining schema of incoming requests'''
from pydantic import BaseModel, Field, model_validator, IPvAnyAddress
from typing import Annotated, Optional, Literal
from datetime import datetime
from server.config import CategoryFlag, ServerConfig

class BaseAuthComponent(BaseModel):
    identity: Annotated[str, Field(min_length=8, max_length=64)]
    password: Optional[Annotated[str, Field(min_length=16, max_length=1024, default=None)]]
    token: Optional[Annotated[str, Field(min_length=16, max_length=1024, default=None)]]
    refresh_digest: Optional[Annotated[str, Field(min_length=ServerConfig.REFRESH_DIGEST_LENGTH.value, max_length=ServerConfig.REFRESH_DIGEST_LENGTH.value, frozen=True, default=None)]]

    @model_validator(mode='after')
    def auth_semantic_check(self) -> 'BaseAuthComponent':
        if not (self.password or self.token):
            raise ValueError('Passkey or token required for authentication')
        if self.refresh_digest and not self.token:
            raise ValueError('Refresh digest provided but no active token given')
        return self
    
class BaseFileComponent(BaseModel):
    subject_file: Annotated[str, Field(max_length=1024, pattern=r'[\w\-\,\@\#\$\%\&\*\(\)\[\]\<\>]{1,64}\.+[a-zA-z]')]
    chunk_number: Optional[Annotated[int, Field(ge=0, frozen=True, default=None)]]
    chunk_size: Optional[Annotated[int, Field(ge=1, le=ServerConfig.CHUNK_MAX_SIZE.value, default=ServerConfig.CHUNK_MAX_SIZE.value)]]
    write_data: Optional[Annotated[str, Field(min_length=1, max_length=ServerConfig.CHUNK_MAX_SIZE.value, frozen=True)]]
    return_partial: Annotated[bool, Field(default=True)]
    cursor_keepalive: Annotated[bool, Field(default=False)]

    @model_validator(mode='after')
    def file_op_semantic_check(self) -> 'BaseFileComponent':
        if not (self.chunk_size or self.write_data):
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
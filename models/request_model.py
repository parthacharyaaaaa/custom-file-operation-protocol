'''Module for defining schema of incoming requests'''
from pydantic import BaseModel, Field, model_validator, IPvAnyAddress, ValidationError
from typing import Annotated, Optional, Literal, Union, TypeAlias
from server.config import ServerConfig
from models.flags import CategoryFlag, PermissionFlags

RequestComponentType: TypeAlias = Union['BaseHeaderComponent', 'BaseAuthComponent', 'BaseFileComponent', 'BasePermissionComponent']

class BaseAuthComponent(BaseModel):
    identity: Annotated[str, Field(min_length=ServerConfig.USERNAME_RANGE.value[0], max_length=ServerConfig.USERNAME_RANGE.value[1], pattern=ServerConfig.USERNAME_REGEX.value)]
    password: Optional[Annotated[str, Field(min_length=ServerConfig.PASSWORD_RANGE.value[0], max_length=ServerConfig.PASSWORD_RANGE.value[1], default=None)]]
    token: Optional[Annotated[str, Field(min_length=16, max_length=1024, default=None)]]
    refresh_digest: Optional[Annotated[str, Field(min_length=ServerConfig.REFRESH_DIGEST_LENGTH.value, max_length=ServerConfig.REFRESH_DIGEST_LENGTH.value, frozen=True, default=None)]]

    @model_validator(mode='after')
    def auth_semantic_check(self) -> 'BaseAuthComponent':
        if not (self.password or self.token):
            raise ValueError('Password or token required for authentication')
        if self.refresh_digest and not self.token:
            raise ValueError('Refresh digest provided but no active token given')
        return self
    
    def auth_logical_check(self, flag: Literal['authorization', 'authentication']) -> bool:
        if flag == 'authorization' and self.password and not (self.token or self.refresh_digest):
            return True
        elif flag == 'authentication' and not self.password and (self.token and self.refresh_digest):
            return True
        
        return False
    
class BaseFileComponent(BaseModel):
    # Target file
    subject_file: Annotated[str, Field(max_length=1024, pattern=ServerConfig.FILENAME_REGEX.value)]

    # Sequencing logic
    cursor_position: Annotated[int, Field(ge=0, frozen=True)]
    chunk_number: Optional[Annotated[int, Field(ge=0, frozen=True, default=None)]]
    chunk_size: Optional[Annotated[int, Field(ge=1, le=ServerConfig.CHUNK_MAX_SIZE.value, default=ServerConfig.CHUNK_MAX_SIZE.value)]]  # For read ops
    write_data: Optional[Annotated[str, Field(min_length=1, max_length=ServerConfig.CHUNK_MAX_SIZE.value, frozen=True)]]    # For write ops
    
    # Attributes exclusive to file reads
    return_partial: Optional[Annotated[bool, Field(default=True)]]
    cursor_keepalive: Optional[Annotated[bool, Field(default=False)]]

    @model_validator(mode='after')
    def file_op_semantic_check(self) -> 'BaseFileComponent':
        if not (self.chunk_size or self.write_data):
            raise ValidationError('Missing any operational data')
        
        if not (self.cursor_position > self.chunk_number):
            raise ValueError('Invalid sequencing logic for reading chunks')
        return self

class BasePermissionComponent(BaseModel):
    # Request subjects
    subject_file: Annotated[str, Field(frozen=True, pattern=ServerConfig.FILENAME_REGEX.value)]
    subject_file_owner: Annotated[str, Field(frozen=True, pattern=ServerConfig.USERNAME_REGEX.value, le=ServerConfig.USERNAME_RANGE.value[0], ge=ServerConfig.USERNAME_RANGE.value[1])]
    subject_user: Optional[Annotated[Union[str, Literal['*']], Field(frozen=True, default=None, pattern=ServerConfig.USERNAME_REGEX.value)]] # + For grnting, - for removal
    
    # Permission data
    permission_flags: Annotated[PermissionFlags, Field(frozen=True)]
    effect_duration: Optional[Annotated[int, Field(le=ServerConfig.EFFECT_DURATION_RANGE.value[0], ge=ServerConfig.EFFECT_DURATION_RANGE.value[1], frozen=True, default=0)]]

    @model_validator(mode='after')
    def permission_logic_check(self) -> 'BasePermissionComponent':
        if (self.permission_flags & (PermissionFlags.TRANSFER.value | PermissionFlags.MANAGER.value)) and self.effect_duration:   # managerial and ownership permissions are high level and cannot be given globally at once
            raise ValueError('Cannot set duration for managerial/ownership roles of a file')
        return self

class BaseHeaderComponent(BaseModel):
    version: Annotated[str, Field(min_length=5, max_length=12, pattern=ServerConfig.VERSION_REGEX.value)]

    # Read ahead logic
    auth_size: Annotated[int, Field(frozen=True, default=0)]
    body_size: Annotated[int, Field(frozen=True, default=0)]

    # Sender metadata
    sender_hostname: Annotated[IPvAnyAddress, Field(frozen=True)]
    sender_port: Annotated[int, Field(frozen=True)]
    sender_timestamp: Annotated[float, Field(frozen=True)]

    # Connection status
    finish: Annotated[bool, Field(frozen=True, default=True)]
    connection_keepalive: Annotated[bool, Field(default=False)]

    # Message category
    category: Annotated[CategoryFlag, Field(frozen=True)]    # 0b0001, 0b0010, 0b0100, and 0b1000
    subcategory: Annotated[int, Field(frozen=True, ge=1)]   # Also bitmask literals, but depending on parent category the number of values can differ
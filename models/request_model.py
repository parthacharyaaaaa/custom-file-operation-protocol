'''Module for defining schema of incoming requests'''
from pydantic import BaseModel, Field, model_validator, IPvAnyAddress, field_serializer
from typing import Annotated, Optional, Literal, Union, TypeAlias
from models.constants import REQUEST_CONSTANTS
from models.flags import CategoryFlag, PermissionFlags, AuthFlags, FileFlags

RequestComponentType: TypeAlias = Union['BaseHeaderComponent', 'BaseAuthComponent', 'BaseFileComponent', 'BasePermissionComponent']

class BaseAuthComponent(BaseModel):
    identity: Annotated[str, Field(min_length=REQUEST_CONSTANTS.auth.username_range[0], max_length=REQUEST_CONSTANTS.auth.username_range[1], pattern=REQUEST_CONSTANTS.auth.username_regex)]
    password: Annotated[Optional[str], Field(min_length=REQUEST_CONSTANTS.auth.password_range[0], max_length=REQUEST_CONSTANTS.auth.password_range[1], default=None)]
    token: Annotated[Optional[bytes], Field(min_length=REQUEST_CONSTANTS.auth.token_length, max_length=REQUEST_CONSTANTS.auth.token_length, default=None)]
    refresh_digest: Annotated[Optional[bytes], Field(min_length=REQUEST_CONSTANTS.auth.digest_length, max_length=REQUEST_CONSTANTS.auth.digest_length, frozen=True, default=None)]

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
    subject_file: Annotated[str, Field(max_length=1024, pattern=REQUEST_CONSTANTS.file.filename_regex)]
    subject_file_owner: Annotated[str, Field(max_length=1024)]

    # Sequencing logic
    cursor_position: Annotated[Optional[int], Field(ge=0, default=None)]
    chunk_size: Annotated[Optional[int], Field(ge=1, le=REQUEST_CONSTANTS.file.chunk_max_size, default=None)]  # For read operations. If specified, must be atleast 1 byte
    write_data: Annotated[Optional[Union[str, bytes, memoryview]], Field(min_length=1, max_length=REQUEST_CONSTANTS.file.chunk_max_size, default=None)]    # For write operations, must be atleast 1 character if specified
    
    # Attributes exclusive to file reads
    return_partial: Annotated[Optional[bool], Field(default=True)]
    cursor_keepalive: Annotated[Optional[bool], Field(default=False)]

    model_config = {
        'arbitrary_types_allowed' : True      
    }

    @field_serializer('write_data', when_used='json-unless-none')
    def serialize_write_data(self, write_data: Union[str, bytes, memoryview]) -> bytes:
        if isinstance(write_data, str): return write_data.encode('utf-8')
        elif isinstance(write_data, memoryview): return bytes(write_data)
        return write_data

class BasePermissionComponent(BaseModel):
    # Request subjects
    subject_file: Annotated[str, Field(frozen=True, pattern=REQUEST_CONSTANTS.file.filename_regex)]
    subject_file_owner: Annotated[str, Field(frozen=True, pattern=REQUEST_CONSTANTS.auth.username_regex,
                                             min_length=REQUEST_CONSTANTS.auth.username_range[0], max_length=REQUEST_CONSTANTS.auth.username_range[1])]
    
    subject_user: Annotated[Optional[str], Field(frozen=True, pattern=REQUEST_CONSTANTS.auth.username_regex,
                                                 min_length=REQUEST_CONSTANTS.auth.username_range[0], max_length=REQUEST_CONSTANTS.auth.username_range[1],
                                                 default=None)]
    
    # Permission data
    effect_duration: Annotated[Optional[int], Field(ge=REQUEST_CONSTANTS.permission.effect_duration_range[0], le=REQUEST_CONSTANTS.permission.effect_duration_range[1], frozen=True, default=0)]

    @staticmethod
    def check_higher_role(permission_bits: int) -> bool:
        # managerial and ownership permissions are high level and cannot be given globally at once
        return (permission_bits & (PermissionFlags.TRANSFER.value | PermissionFlags.MANAGER.value))

class BaseHeaderComponent(BaseModel):
    version: Annotated[str, Field(min_length=5, max_length=12, pattern=REQUEST_CONSTANTS.header.version_regex)]

    # Read ahead logic
    auth_size: Annotated[int, Field(ge=0, default=0)]
    body_size: Annotated[int, Field(ge=0, default=0)]

    # Sender metadata
    sender_hostname: Annotated[IPvAnyAddress, Field(frozen=True)]
    sender_port: Annotated[int, Field(frozen=True)]
    sender_timestamp: Annotated[float, Field(frozen=True)]

    # Connection status
    finish: Annotated[bool, Field(default=False)]

    # Message category
    category: Annotated[CategoryFlag, Field(frozen=True, ge=1)]
    subcategory: Annotated[Union[AuthFlags, PermissionFlags, FileFlags], Field(frozen=True, ge=1)]


    model_config = {
        'use_enum_values' : True
    }
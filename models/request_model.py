'''Module for defining schema of incoming requests'''
from pathlib import Path
from typing import Annotated, Optional, Literal, Union, TYPE_CHECKING

from models.constants import REQUEST_CONSTANTS
from models.flags import CategoryFlag, PermissionFlags, AuthFlags, FileFlags, InfoFlags
from models.cursor_flag import CURSOR_BITS_CHECK

from pydantic import BaseModel, Field, model_validator, IPvAnyAddress, field_serializer, field_validator

if TYPE_CHECKING: assert REQUEST_CONSTANTS

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
    subject_file: str = Field(max_length=1024, pattern=REQUEST_CONSTANTS.file.filename_regex)
    subject_file_owner: str = Field(max_length=1024)

    # Sequencing logic
    cursor_position: Optional[int] = Field(default=None, ge=0)
    chunk_size: int = Field(default=REQUEST_CONSTANTS.file.chunk_max_size, ge=1, le=REQUEST_CONSTANTS.file.chunk_max_size)  # For read operations. Must be at least 1 byte if specified
    write_data: Optional[bytes] = Field(default=None, min_length=1, max_length=REQUEST_CONSTANTS.file.chunk_max_size)  # For write operations, must be at least 1 byte if specified

    # Attributes exclusive to file operations
    cursor_bitfield: int = Field(default=0, ge=0)
    end_operation: bool = Field(default=True)

    model_config = {
        'arbitrary_types_allowed' : True
    }

    @field_serializer('write_data', when_used='always')
    def serialize_write_data(self, write_data: Union[str, bytes, memoryview]) -> bytes:
        if isinstance(write_data, str): return write_data.encode('utf-8')
        elif isinstance(write_data, memoryview): return bytes(write_data)
        return write_data

    @field_validator('cursor_bitfield', mode='after')
    @classmethod
    def validate_cursor_bitfield(cls, bits: int) -> int:
        if (bits & ~CURSOR_BITS_CHECK):
            raise ValueError('Unrecognised flags provided in cursor bitfield')
        return bits
    
    @field_validator('write_data', mode='before')
    @classmethod
    def cast_write_data(cls, write_data: Union[str, bytes, bytearray, memoryview]) -> bytes:
        if isinstance(write_data, str): return write_data.encode(encoding='utf-8')
        elif isinstance(write_data, Union[bytearray, memoryview]): return bytes(write_data)
        return write_data
    
    @property
    def relative_pathlike(self) -> str:
        return f'{self.subject_file_owner}/{self.subject_file}'
    
    @property
    def relative_path(self) -> Path:
        return Path(self.relative_pathlike)

class BasePermissionComponent(BaseModel):
    # Request subjects
    subject_file: str = Field(pattern=REQUEST_CONSTANTS.file.filename_regex, frozen=True)
    
    subject_file_owner: str = Field(
        pattern=REQUEST_CONSTANTS.auth.username_regex,
        min_length=REQUEST_CONSTANTS.auth.username_range[0],
        max_length=REQUEST_CONSTANTS.auth.username_range[1],
        frozen=True
    )
    
    subject_user: Optional[str] = Field(
        default=None,
        pattern=REQUEST_CONSTANTS.auth.username_regex,
        min_length=REQUEST_CONSTANTS.auth.username_range[0],
        max_length=REQUEST_CONSTANTS.auth.username_range[1],
        frozen=True
    )
    
    # Permission data
    effect_duration: Optional[int] = Field(
        default=0,
        ge=REQUEST_CONSTANTS.permission.effect_duration_range[0],
        le=REQUEST_CONSTANTS.permission.effect_duration_range[1],
        frozen=True
    )

    @staticmethod
    def check_higher_role(permission_bits: int) -> bool:
        # managerial and ownership permissions are high level and cannot be given globally at once
        return bool(permission_bits & (PermissionFlags.TRANSFER.value | PermissionFlags.MANAGER.value))

class BaseInfoComponent(BaseModel):
    subject_resource: Annotated[Optional[str], Field(default=None)]


class BaseHeaderComponent(BaseModel):
    version: str = Field(min_length=5, max_length=12, pattern=REQUEST_CONSTANTS.header.version_regex)
    
    # Read ahead logic
    auth_size: int = Field(default=0, ge=0)
    body_size: int = Field(default=0, ge=0)
    
    # Sender metadata
    sender_hostname: IPvAnyAddress = Field(frozen=True)
    sender_port: int = Field(frozen=True)
    sender_timestamp: float = Field(frozen=True)
    
    # Connection status
    finish: bool = Field(default=False)
    
    # Message category
    category: CategoryFlag = Field(ge=1)
    subcategory: Union[AuthFlags, PermissionFlags, InfoFlags, FileFlags]
'''Module for defining schema of the protocol'''
from pydantic import BaseModel, Field, model_validator, IPvAnyAddress
from typing import Annotated, Optional, Literal

class BaseAuthComponent(BaseModel):
    identity: Annotated[bytes, Field(min_length=8, max_length=64)]
    password: Optional[Annotated[bytes, Field(min_length=16, max_length=1024)]]
    token: Optional[Annotated[bytes, Field(min_length=16, max_length=1024)]]
    
    register: Optional[Annotated[bool, Field(default=False)]]
    max_time: Annotated[int, Field(ge=16, le=86400)]

    @model_validator(mode='after')
    def auth_semantic_check(self) -> 'BaseAuthComponent':
        if not (self.password or self.token):
            raise ValueError('Passkey or token required for authentication')
        return self
    
    @model_validator(mode='after')
    def register_semantic_check(self) -> 'BaseAuthComponent':
        if self.register:
            if self.token:
                raise ValueError('Registration requires token field to be empty')
            if not (self.identity and self.password):
                raise ValueError('Registration requires both identity and password to be required')
        return self
    
class BaseBodyComponent(BaseModel):
    file: Annotated[bytes, Field(pattern=r'[\w]{1,64}(.[\w]{1,64}*).[\w]{1,64}', ge=4)]
    mode: Literal[b'r', b'w', b'a', b'd', b'c']
    byte_length: Optional[Annotated[int, Field(le=-1, ge=4096)]]
    delete_after: Annotated[bool, Field(default=False)]

    @model_validator(mode='after')
    def mode_validation(self) -> 'BaseAuthComponent':
        if self.mode == b'd' and self.delete_after:
            self.delete_after = False
        if self.mode == b'c' and self.delete_after:
            raise ValueError('It is forbidden to delete a file right after creation')
        if self.mode == b'r' and not self.byte_length:
            self.byte_length = -1   # Special value to read entire file
        return self
    

class BaseHeaderComponent(BaseModel):
    version: Annotated[int, Field(ge=0)]
    size: Annotated[int, Field(ge=2116)]
    sender_address: IPvAnyAddress

class BaseWire(BaseModel):
    header: BaseHeaderComponent
    auth: BaseAuthComponent
    body: BaseBodyComponent
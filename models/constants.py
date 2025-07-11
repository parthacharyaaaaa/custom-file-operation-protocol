import os
from typing import Annotated, Any
import pytomlpp
from pydantic import BaseModel, Field

class HeaderRequestConstants(BaseModel):
    version_regex: Annotated[str, Field(frozen=True)]
    max_bytesize: Annotated[int, Field(frozen=True)]

class FileRequestConstants(BaseModel):
    max_bytesize: Annotated[int, Field(frozen=True)]
    filename_regex: Annotated[str, Field(frozen=True)]
    chunk_max_size: Annotated[int, Field(frozen=True)]

class AuthRequestConstants(BaseModel):
    max_bytesize: Annotated[int, Field(frozen=True)]
    username_regex: Annotated[str, Field(frozen=True)]
    username_range: tuple[
        Annotated[int, Field(frozen=True)],
        Annotated[int, Field(frozen=True)]
        ]
    
    password_range: tuple[
        Annotated[int, Field(frozen=True, ge=0)],
        Annotated[int, Field(frozen=True, ge=0)]
        ]
    
    digest_length: Annotated[int, Field(frozen=True)]
    token_length: Annotated[int, Field(frozen=True)]

class PermissionRequestConstants(BaseModel):
    max_bytesize: Annotated[int, Field(frozen=True, ge=0)]
    effect_duration_range: tuple[
        Annotated[int, Field(frozen=True, ge=0)],
        Annotated[int, Field(frozen=True, ge=0)]
        ]

class HeaderResponseConstants(BaseModel):
    code_regex: str
    bytesize: Annotated[int, Field(frozen=True, ge=1)]

class RequestConstants(BaseModel):
    header: HeaderRequestConstants
    auth: AuthRequestConstants
    file: FileRequestConstants
    permission: PermissionRequestConstants

class ResponseConstants(BaseModel):
    header: HeaderResponseConstants

REQUEST_CONSTANTS: RequestConstants = None
RESPONSE_CONSTANTS: ResponseConstants = None

def load_constants():
    global REQUEST_CONSTANTS, RESPONSE_CONSTANTS
    loaded_constants: dict[str, Any] = pytomlpp.load(os.path.join(os.path.dirname(__file__), 'constants.toml'))
    REQUEST_CONSTANTS = RequestConstants.model_validate({'header' : HeaderRequestConstants.model_validate(loaded_constants['components']['request']['header']),
                                                         'auth' : AuthRequestConstants.model_validate(loaded_constants['components']['request']['auth']),
                                                         'file' : FileRequestConstants.model_validate(loaded_constants['components']['request']['file']),
                                                         'permission' : PermissionRequestConstants.model_validate(loaded_constants['components']['request']['permission'])})
    
    RESPONSE_CONSTANTS = ResponseConstants.model_validate({'header' : HeaderResponseConstants.model_validate(loaded_constants['components']['response']['header'])})

    return REQUEST_CONSTANTS, RESPONSE_CONSTANTS
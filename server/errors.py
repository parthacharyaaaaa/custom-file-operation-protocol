from abc import ABC
from datetime import datetime
from typing import Optional
from models.flags import CategoryFlag
from models.response_codes import ClientErrorFlags, ServerErrorFlags

__all__ = ('ProtocolException', 'SlowStreamRate', 'InvalidHeaderSemantic', 'InvalidHeaderValues', 'InvalidAuthSemantic', 'InvalidAuthData', 'InvalidFileData', 'UnsupportedOperation', 'UserAuthenticationError', 'UserNotFound', 'InsufficientPermissions', 'OperationalConflict', 'OperationContested', 'Banned', 'FileNotFound', 'FileConflict', 'FileContested', 'InternalServerError', 'DatabaseFailure')

class ProtocolException(ABC, Exception):
    '''Abstract base exception class for all protocol specific exceptions. Contains all the bare minimum data required to construct and send a response to an erroneous request'''
    code: str
    description: str
    exception_iso_timestamp: str

    def __init__(self, description: Optional[str] = None):
        self.description = description or self.__class__.description
        self.exception_iso_timestamp = datetime.now().isoformat()


# Client side errors
class SlowStreamRate(ProtocolException):
    code: str = ClientErrorFlags.UNACCEPTABLE_SPEED.value
    description: str = 'Stream rate unacceptable, ensure proper network connection'

class InvalidHeaderSemantic(ProtocolException):
    code: str = ClientErrorFlags.INVALID_HEADER_SEMANTIC.value
    description: str = 'Header semantics incorrect, please ensure that all necessary fields are present'

class InvalidHeaderValues(ProtocolException):
    code: str = ClientErrorFlags.INVALID_HEADER_VALUES.value
    description: str = 'Header values incorrect'

class InvalidAuthSemantic(ProtocolException):
    code: str = ClientErrorFlags.INVALID_AUTH_SEMANTIC.value
    description: str = 'Auth semantics incorrect, please ensure that all necessary fields are present'

class InvalidAuthData(ProtocolException):
    code: str = ClientErrorFlags.INCORRECT_AUTH_DATA.value
    description: str = 'Auth values incorrect'

class InvalidFileData(ProtocolException):
    code: str = ClientErrorFlags.INVALID_FILE_DATA.value
    description: str = 'Invalid file component data'

class InvalidBodyValues(ProtocolException):
    code: str = ClientErrorFlags.INVALID_BODY_VALUE.value
    description: str = 'Invalid body data'


class UnsupportedOperation(ProtocolException):
    code: str = ClientErrorFlags.UNSUPPORTED_OPERATION.value
    description: str = f'Unsupported Operation requested. Must be: {", ".join(CategoryFlag._member_names_)}'

class UserAuthenticationError(ProtocolException):
    code: str = ClientErrorFlags.USER_AUTHENTICATION_ERROR.value
    description: str = 'User authentication error'

class UserNotFound(ProtocolException):
    code: str = ClientErrorFlags.USER_NOT_FOUMD.value
    description: str = "User not found"

class InsufficientPermissions(ProtocolException):
    code: str = ClientErrorFlags.INSUFFICIENT_PERMISSIONS.value
    description: str = 'Insufficient permissions for this action'

class OperationalConflict(ProtocolException):
    code: str = ClientErrorFlags.OPERATIONAL_CONFLICT.value
    description: str = 'Operational conflict'

class Banned(ProtocolException):
    code: str = ClientErrorFlags.BANNED.value
    description: str = 'User {username} is banned'

    def __init__(self, username: str, description: Optional[str] = None):
        super().__init__(description or Banned.description)
        self.description.format(username=username)

class FileNotFound(ProtocolException):
    code: str = ClientErrorFlags.FILE_NOT_FOUND.value
    description: str = 'No file named {file} under {username} found'

    def __init__(self, file: str, username: str, description: Optional[str] = None):
        super().__init__(description or FileNotFound.description)
        self.description.format(file=file, username=username)

class FileContested(ProtocolException):
    code: str = ClientErrorFlags.FILE_CONTESTED.value
    description: str = 'File named {file} under {username} found is currently contested'

    def __init__(self, file: str, username: str, description: Optional[str] = None):
        super().__init__(description or FileContested.description)
        self.description.format(file=file, username=username)

class FileConflict(ProtocolException):
    code: str = ClientErrorFlags.FILE_CONFLICT.value
    description: str = 'Conflicting operation for file named {file} under {username}'

    def __init__(self, file: str, username: str, description: Optional[str] = None):
        super().__init__(description or Banned.description)
        self.description.format(file=file, username=username)

class OperationContested(ProtocolException):
    code: str = ClientErrorFlags.OPERATION_CONTESTED.value
    description: str = 'Operation contested'


# Server side errors
class InternalServerError(ProtocolException):
    code: str = ServerErrorFlags.INTERNAL_SERVER_ERROR.value
    description: str = 'Internal Server Error'

class DatabaseFailure(ProtocolException):
    code: str = ServerErrorFlags.DATABASE_FAILURE.value
    description: str = 'Database failure'

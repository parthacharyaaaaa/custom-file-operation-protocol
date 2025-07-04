from abc import ABC
from datetime import datetime
from typing import Optional
from server.config import CategoryFlag

class ProtocolException(ABC, BaseException):
    '''Abstract base exception class for all protocol specific exceptions. Contains all the bare minimum data required to construct and send a response to an erroneous request'''
    code: str
    description: str
    exception_iso_timestamp: datetime

    def __init__(self, description: str):
        self.description = description
        self.exception_iso_timestamp = datetime.now().isoformat()

class SlowStreamRate(ProtocolException):
    code: str = '2:us'
    description: str = 'Stream rate too slow, ensure proper network connection'

class InvalidHeaderSemantic(ProtocolException):
    code: str = '2:ihs'
    description: str = 'Header semantics incorrect, please ensure that all necessary fields are present'

class InvalidHeaderValues(ProtocolException):
    code: str = '2:ihv'
    description: str = 'Header values incorrect'

class InvalidAuthSemantic(ProtocolException):
    code: str = '2:ias'
    description: str = 'Auth semantics incorrect, please ensure that all necessary fields are present'

class InvalidAuthData(ProtocolException):
    code: str = '2:iad'
    description: str = 'Auth values incorrect'

class UnsupportedOperation(ProtocolException):
    code: str = '2:iad'
    description: str = f'Unsupported Operation requested. Must be: {", ".join(CategoryFlag._member_names_)}'

class InternalServerError(ProtocolException):
    code: str = '3:*'
    description: str = 'Internal Server Error'

class UserAuthenticationError(ProtocolException):
    code: str = '2:exu'
    description: str = 'User authentication error'

class InsufficientPermissions(ProtocolException):
    code: str = '2:perm'
    description: str = 'Insufficient permissions for this action'

class Banned(ProtocolException):
    code: str = '2:ban'
    description: str = 'User {username} is banned'

    def __init__(self, username: str, description: Optional[str] = None):
        super().__init__(description or Banned.description)
        self.description.format(username=username)

class FileNotFound(ProtocolException):
    code: str = '2:nf'
    description: str = 'No file named {file} under {username} found'

    def __init__(self, file: str, username: str, description: Optional[str] = None):
        super().__init__(description or Banned.description)
        self.description.format(file=file, username=username)

class FileConflict(ProtocolException):
    code: str = '2:cnf'
    description: str = 'Conflicting operation for file named {file} under {username}'

    def __init__(self, file: str, username: str, description: Optional[str] = None):
        super().__init__(description or Banned.description)
        self.description.format(file=file, username=username)

class DatabaseFailure(ProtocolException):
    code: str = '3:db'
    description: str = 'Database failure'

class OperationContested(ProtocolException):
    code: str = '3:opc'
    description: str = 'Operation contested'

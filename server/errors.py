from abc import ABC
from datetime import datetime
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
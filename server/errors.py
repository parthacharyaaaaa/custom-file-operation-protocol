from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime

@dataclass(frozen=True, slots=True)
class ProtocolException(ABC, BaseException):
    '''Abstract base exception class for all protocol specific exceptions. Contains all the bare minimum data required to construct and send a response to an erroneous request'''
    code: str
    description: str
    exception_iso_timestamp: str = field(default_factory=datetime.now().isoformat())

@dataclass(frozen=True, slots=True)
class SlowStreamRate(ProtocolException):
    code: str = '2:us'
    description: str = 'Stream rate too slow, ensure proper network connection'

@dataclass(frozen=True, slots=True)
class InvalidHeaderSemantic(ProtocolException):
    code: str = '2:ihs'
    description: str = 'Header semantics incorrect, please ensure that all necessary fields are present'

@dataclass(frozen=True, slots=True)
class InvalidHeaderValues(ProtocolException):
    code: str = '2:ihv'
    description: str = 'Header values incorrect'


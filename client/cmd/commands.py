'''Module containing string representations of commands available to the client'''
from enum import Enum

class AuthCommands(Enum):
    AUTH: str = 'AUTH'
    UNEW: str = 'UNEW'
    UDEL: str = 'UDEL'
    STERM: str = 'STERM'
    SREF: str = 'SREF'

class FileCommands(Enum):
    CREATE: str = 'CREATE'
    DELETE: str = 'DELETE'
    UPLOAD: str = 'UPLOAD'
    READ: str = 'READ'
    APPEND: str = 'APPEND'
    WRITE: str = 'WRITE'

class PermissionCommands(Enum):
    GRANT: str = 'GRANT'
    REVOKE: str = 'REVOKE'
    PUBLICISE: str = 'PUBLICISE'
    HIDE: str = 'HIDE'
    TRANSFER: str = 'TRANSFER'

class HeartbeatCommands(Enum):
    HEARTBEAT: str = 'HEARTBEAT'

class GeneralModifierCommands(Enum):
    END_CONNECTION: str = 'BYE'
    CURSOR_KEEPALIVE: str = 'CK'
    RETURNED_PARTIAL: str = 'RP'
    DISPLAY_CREDENTIALS: str = 'DC'
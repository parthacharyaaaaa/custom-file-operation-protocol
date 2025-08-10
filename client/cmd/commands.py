'''Module containing string representations of commands available to the client'''
from enum import Enum

class AuthCommands(Enum):
    AUTH: str = 'AUTH'
    UNEW: str = 'UNEW'
    UDEL: str = 'UDEL'
    STERM: str = 'STERM'
    SREF: str = 'SREF'

class FileCommands(Enum):
    CREATE      = 'create'
    DELETE      = 'delete'
    UPLOAD      = 'upload'
    READ        = 'read'
    APPEND      = 'append'
    PATCH       = 'patch'
    REPLACE     = 'replace'

class PermissionCommands(Enum):
    GRANT: str = 'GRANT'
    REVOKE: str = 'REVOKE'
    PUBLICISE: str = 'PUBLICISE'
    HIDE: str = 'HIDE'
    TRANSFER: str = 'TRANSFER'

class HeartbeatCommands(Enum):
    HEARTBEAT: str = 'HEARTBEAT'

class FileModifierCommands(Enum):
    WRITE_DATA                          = 'write_data'
    CURSOR_KEEPALIVE                    = 'keepalive'
    POST_OPERATION_CURSOR_KEEPALIVE     = 'post-keepalive'
    PURGE_CURSOR                        = 'purge'
    CHUNK_SIZE                          = 'chunk-size'
    CHUNKED                             = 'chunked'
    POSITION                            = 'position'
    LIMIT                               = 'limit'


class GeneralModifierCommands(Enum):
    END_CONNECTION: str = 'BYE'

class AuthModifierCommands(Enum):
    DISPLAY_CREDENTIALS: str = 'DC'

class PermissionModifierCommands(Enum):
    GRANT_DURATION: str = 'GD'
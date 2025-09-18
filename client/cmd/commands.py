'''Module containing string representations of commands available to the client'''

from enum import Enum
from models.flags import InfoFlags
from types import MappingProxyType
from typing import Final

__all__ = ('AuthCommands', 'FileCommands', 'PermissionCommands', 'QueryTypes', 'QueryMapper', 'FileModifierCommands', 'GeneralModifierCommands', 'AuthModifierCommands', 'PermissionModifierCommands')

class AuthCommands(Enum):
    AUTH    = 'AUTH'
    UNEW    = 'UNEW'
    UDEL    = 'UDEL'
    STERM   = 'STERM'
    SREF    = 'SREF'

class FileCommands(Enum):
    CREATE      = 'create'
    DELETE      = 'delete'
    UPLOAD      = 'upload'
    READ        = 'read'
    APPEND      = 'append'
    PATCH       = 'patch'
    REPLACE     = 'replace'

class PermissionCommands(Enum):
    GRANT       = 'GRANT'
    REVOKE      = 'REVOKE'
    PUBLICISE   = 'PUBLICISE'
    HIDE        = 'HIDE'
    TRANSFER    = 'TRANSFER'

class QueryTypes(Enum):
    FILE_METADATA           = 'file'
    PERMISSION_METADATA     = 'permission'
    USER_METADATA           = 'user'
    STORAGE_USAGE           = 'storage'

QueryMapper: Final[MappingProxyType[QueryTypes, InfoFlags]] = MappingProxyType(
    {
        QueryTypes.FILE_METADATA        : InfoFlags.FILE_METADATA,
        QueryTypes.PERMISSION_METADATA  : InfoFlags.PERMISSION_METADATA,
        QueryTypes.USER_METADATA        : InfoFlags.USER_METADATA,
        QueryTypes.STORAGE_USAGE        : InfoFlags.STORAGE_USAGE
    }
)

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
    END_CONNECTION = 'BYE'

class AuthModifierCommands(Enum):
    DISPLAY_CREDENTIALS = 'DC'

class PermissionModifierCommands(Enum):
    GRANT_DURATION = 'GD'
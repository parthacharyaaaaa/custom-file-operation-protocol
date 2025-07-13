from enum import Enum
from types import MappingProxyType
from models.flags import PermissionFlags

__all__ = ('RoleTypes', 'FilePermissions', 'ROLE_MAPPING',)

class RoleTypes(Enum):
    OWNER       = 'owner'
    MANAGER     = 'manager'
    READER      = 'reader'
    EDITOR      = 'editor'

class FilePermissions(Enum):
    WRITE           = 'write'
    READ            = 'read'
    DELETE          = 'delete'
    MANAGE_SUPER    = 'manage_super'
    MANAGE_RW       = 'manage_rw'


ROLE_MAPPING: MappingProxyType[PermissionFlags, RoleTypes] = MappingProxyType(
    {
        PermissionFlags.READER : RoleTypes.READER,
        PermissionFlags.EDITOR : RoleTypes.EDITOR,
        PermissionFlags.MANAGER : RoleTypes.MANAGER
    }
)
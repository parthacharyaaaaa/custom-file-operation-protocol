from server.database.models import RoleTypes
from models.flags import PermissionFlags
from types import MappingProxyType

__all__ = ('ROLE_MAPPING',)

ROLE_MAPPING: MappingProxyType[PermissionFlags, RoleTypes] = MappingProxyType(
    {
        PermissionFlags.READER : RoleTypes.READER,
        PermissionFlags.EDITOR : RoleTypes.EDITOR,
        PermissionFlags.MANAGER : RoleTypes.MANAGER
    }
)
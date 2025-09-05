from typing import Final
from types import MappingProxyType

from models.flags import CategoryFlag, AuthFlags, PermissionFlags, InfoFlags, FileFlags

from server.authz.auth_handler import top_auth_handler
from server.info_ops.info_handler import top_info_handler
from server.file_ops.file_handler import top_file_handler
from server.permission_ops.permission_handler import top_permission_handler
from server.info_ops import info_subhandlers
from server.authz import auth_subhandlers

from server.permission_ops import permission_subhandlers
from server.file_ops import file_subhandlers

from server.typing import AuthSubhandler, InfoSubhandler, FileSubhandler, PermissionSubhandler, TopRequestHandler

__all__ = ('TOP_LEVEL_REQUEST_MAPPING',
           'AUTH_SUBHABDLER_MAPPING',
           'INFO_SUBHANDLER_MAPPING',
           'PERMISSION_SUBHANDLER_MAPPING',
           'FILE_SUBHANDLER_MAPPING')

TOP_LEVEL_REQUEST_MAPPING: Final[MappingProxyType[CategoryFlag, TopRequestHandler]] = MappingProxyType(
    {
        CategoryFlag.AUTH : top_auth_handler,
        CategoryFlag.INFO : top_info_handler,
        CategoryFlag.FILE_OP : top_file_handler,
        CategoryFlag.PERMISSION : top_permission_handler
    }
)

AUTH_SUBHABDLER_MAPPING: Final[dict[AuthFlags, AuthSubhandler]] = {
    AuthFlags.REGISTER : auth_subhandlers.handle_registration,
    AuthFlags.LOGIN : auth_subhandlers.handle_login,
    AuthFlags.REFRESH : auth_subhandlers.handle_session_refresh,
    AuthFlags.LOGOUT : auth_subhandlers.handle_session_termination,
    AuthFlags.CHANGE_PASSWORD : auth_subhandlers.handle_password_change,
    AuthFlags.DELETE : auth_subhandlers.handle_deletion
}

INFO_SUBHANDLER_MAPPING: Final[dict[InfoFlags, InfoSubhandler]] = {
    InfoFlags.HEARTBEAT : info_subhandlers.handle_heartbeat,
    InfoFlags.PERMISSION_METADATA : info_subhandlers.handle_permission_query,
    InfoFlags.FILE_METADATA : info_subhandlers.handle_filedata_query,
    InfoFlags.USER_METADATA : info_subhandlers.handle_user_query,
    InfoFlags.STORAGE_USAGE : info_subhandlers.handle_storage_query,
    InfoFlags.SSL_CREDENTIALS : info_subhandlers.handle_ssl_query
}

PERMISSION_SUBHANDLER_MAPPING: Final[dict[PermissionFlags, PermissionSubhandler]] = {
    PermissionFlags.GRANT : permission_subhandlers.grant_permission,
    PermissionFlags.REVOKE : permission_subhandlers.revoke_permission,
    PermissionFlags.HIDE : permission_subhandlers.hide_file,
    PermissionFlags.PUBLICISE : permission_subhandlers.publicise_file,
    PermissionFlags.TRANSFER : permission_subhandlers.publicise_file
}

# Write, append, and overwrite share the same handler
FILE_SUBHANDLER_MAPPING: Final[dict[FileFlags, FileSubhandler]] = {
    FileFlags.CREATE : file_subhandlers.handle_creation,
    FileFlags.WRITE : file_subhandlers.handle_amendment,
    FileFlags.APPEND : file_subhandlers.handle_amendment,
    FileFlags.OVERWRITE : file_subhandlers.handle_amendment,
    FileFlags.READ : file_subhandlers.handle_read,
    FileFlags.DELETE : file_subhandlers.handle_deletion
}
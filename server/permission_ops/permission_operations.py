import orjson
import psycopg.errors as pg_exc
from psycopg.rows import Row, dict_row
from server.bootup import connection_master
from response_codes import SuccessFlags
from server.connectionpool import ConnectionProxy
from server.database.models import role_types
from server.errors import OperationContested, DatabaseFailure, FileNotFound, FileConflict, InsufficientPermissions, OperationalConflict
from server.models.request_model import BaseHeaderComponent, BaseAuthComponent, BasePermissionComponent
from server.models.response_models import ResponseHeader, ResponseBody
from server.permission_ops.permission_flags import PermissionFlags
from typing import Any, Optional, Literal, Sequence
from datetime import datetime

# TODO: Add logging for database-related failures

async def check_file_permission(filename: str, owner: str, grantee: str, check_for: Sequence[role_types], proxy: Optional[ConnectionProxy] = None, level: Optional[Literal[1,2,3]] = 1) -> bool:
    reclaim_after: bool = proxy is None
    if not proxy:
        proxy: ConnectionProxy = await connection_master.request_connection(level=level)
    try:
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(''''SELECT role
                                 FROM file_permissions
                                 WHERE file_owner = %s AND filename = %s AND grantee = %s;''',
                                 (owner, filename, grantee,))
            role_mapping: dict[str, role_types] = await cursor.fetchone()
            if not role_mapping:
                return False
            return role_mapping['role'] in check_for
    finally:
        if reclaim_after:
            await connection_master.reclaim_connection(proxy)


async def publicise_file(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, permission_component: BasePermissionComponent) -> tuple[ResponseHeader, None]:
    proxy: ConnectionProxy = connection_master.request_connection(level=1)
    try:
        async with proxy.cursor(row_factory=dict_row) as cursor:
            # Only owner is allowed to publicise/hide files
            await cursor.execute('''SELECT public
                                 FROM files
                                 WHERE owner = %s AND filename = %s
                                 FOR UPDATE NOWAIT;''',
                                 (auth_component.identity, permission_component.subject_file,))
            
            result: dict[str, bool] = await cursor.fetchone()
            if not result:
                raise FileNotFound(file=permission_component.subject_file, username=auth_component.identity)
            if result['public']:   # File already public
                raise FileConflict(file=permission_component.subject_file, username=auth_component.identity)
            
            await cursor.execute('''UPDATE files
                                 SET public = TRUE
                                 WHERE owner = %s AND filename = %s;''',
                                 (auth_component.identity, permission_component.subject_file,))
        await proxy.commit()
    except pg_exc.LockNotAvailable:
        raise OperationContested
    except pg_exc.Error:
        raise DatabaseFailure('Failed to publicise file')
    finally:
        connection_master.reclaim_connection(proxy)

    return ResponseHeader(version=header_component.version, code=SuccessFlags.SUCCESSFUL_FILE_PUBLICISE.value, ended_connection=header_component.finish), None


async def hide_file(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, permission_component: BasePermissionComponent) -> tuple[ResponseHeader, ResponseBody]:
    proxy: ConnectionProxy = connection_master.request_connection(level=1)
    try:
        async with proxy.cursor(row_factory = dict_row) as cursor:
            # Only owner is allowed to publicise/hide files
            await cursor.execute('''SELECT *
                                 FROM files
                                 WHERE owner = %s AND filename = %s
                                 FOR UPDATE NOWAIT;''',
                                 (auth_component.identity, permission_component.subject_file,))
            
            file_mapping: dict[str, Any] = await cursor.fetchone()
            if not file_mapping:
                raise FileNotFound(file=permission_component.subject_file, username=auth_component.identity)

            await cursor.execute('''UPDATE files
                                 SET public = FALSE
                                 WHERE owner = %s AND filename = %s;''',
                                 (auth_component.identity, permission_component.subject_file,))
            
            await cursor.execute('''DELETE FROM file_permissions
                                 WHERE file_owner = %s AND filename = %s
                                 RETURNING grantee, role;''',
                                 (auth_component.identity, permission_component.subject_file,))
            
            revoked_grantees: list[dict[str, str]] = await cursor.fetchall()
        await proxy.commit()
    except pg_exc.LockNotAvailable:
        raise OperationContested
    except pg_exc.Error:
        raise DatabaseFailure('Failed to hide file')
    finally:
        connection_master.reclaim_connection(proxy)

    return ResponseHeader(version=header_component.version, code=SuccessFlags.SUCCESSFUL_FILE_HIDE.value, ended_connection=header_component.finish), ResponseBody(contents=orjson.dumps({'revoked_grantee_info' : revoked_grantees}))

async def grant_permission(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, permission_component: BasePermissionComponent) -> tuple[ResponseHeader, None]:
    allowed_roles: list[role_types] = ['manager', 'owner']
    if (permission_component.permission_flags & PermissionFlags.MANAGER.value): # If request is to grant manager role to a user, then only the owner of this file is allowed
        allowed_roles.remove('manager')
    
    proxy: ConnectionProxy = await connection_master.request_connection(level=2)
    try:
        if not await check_file_permission(permission_component.subject_file, permission_component.subject_file_owner, permission_component.subject_user, check_for=allowed_roles, proxy=proxy):
            raise InsufficientPermissions
        
        async with proxy.cursor() as cursor:
            await cursor.execute('''SELECT role, granted_by
                                 FROM file_permissions
                                 WHERE file_owner = %s AND filename = %s AND grantee = %s
                                 FOR UPDATE NOWAIT;''',
                                 (permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user,))
            permission_mapping: dict[str, str] = await cursor.fetchone()
            requested_role: role_types = PermissionFlags._value2member_map_[permission_component.permission_flags & 0b11100000] # Most significant 3 bits reserved for role
            if permission_mapping:
                if requested_role == permission_mapping['role']:
                    raise OperationalConflict(f'User {permission_component.subject_user} already has permission {requested_role} on file {permission_component.subject_file} owned by {permission_component.subject_file_owner}')
                
                # Overriding a role must require new granter to have same or higher permissions than previous granter.
                # Manager -> manager overrides, including overriding an ex-manager is allowed so no checks needed.
                # However, if file owner is the granter, then only the owner themselves are allowed   
                elif (permission_mapping['granted_by'] == permission_component.subject_file_owner) and (auth_component.identity != permission_component.subject_file_owner):
                    raise InsufficientPermissions(f'Insufficient permission to override role of user {permission_component.subject_user} on file {permission_component.subject_file} owned by {permission_component.subject_file_owner} (role previosuly granted by {permission_component["granted_by"]})')
            await cursor.execute('''UPDATE file_permissions
                                 SET role = %s, granted_at = %s, granted_by = %s
                                 WHERE file_owner = %s AND filename = %s AND grantee = %s''',
                                 (requested_role, datetime.now(), auth_component.identity,
                                  permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user,))
        await proxy.commit()
    except pg_exc.LockNotAvailable:
        raise OperationContested
    except pg_exc.Error:
        raise DatabaseFailure('Failed to hide file')
    finally:
        await connection_master.reclaim_connection(proxy)
    
    return ResponseHeader(version=header_component.version, code=SuccessFlags.SUCCESSFUL_GRANT, ended_connection=header_component.finish), None
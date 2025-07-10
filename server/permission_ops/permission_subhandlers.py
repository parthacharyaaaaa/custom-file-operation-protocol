import asyncio
from datetime import datetime
import orjson
import os
from typing import Any, Optional, Literal, Sequence
from traceback import format_exception_only

from models.flags import PermissionFlags
from models.response_models import ResponseHeader, ResponseBody
from models.response_codes import SuccessFlags
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BasePermissionComponent

import psycopg.errors as pg_exc
from psycopg.rows import Row, dict_row

from server.bootup import connection_master
from server.bootup import read_cache, write_cache, append_cache, delete_cache, log_queue
from server.config.server_config import SERVER_CONFIG
from server.connectionpool import ConnectionProxy
from server.database.models import role_types, ActivityLog, LogType, LogAuthor, Severity
from server.errors import OperationContested, DatabaseFailure, FileNotFound, FileConflict, InsufficientPermissions, OperationalConflict
from server.file_ops.base_operations import transfer_file
from server.logging import enqueue_log

async def check_file_permission(filename: str, owner: str, grantee: str, check_for: Sequence[role_types], proxy: Optional[ConnectionProxy] = None, level: Optional[Literal[1,2,3]] = 1) -> bool:
    reclaim_after: bool = proxy is None
    if not proxy:
        proxy: ConnectionProxy = await connection_master.request_connection(level=level)
    try:
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(''''SELECT role
                                 FROM file_permissions
                                 WHERE file_owner = %s AND filename = %s AND grantee = %s AND granted_until > %s;''',
                                 (owner, filename, grantee, datetime.now(),))
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
    except pg_exc.Error as e:
        asyncio.create_task(
                enqueue_log(waiting_period=SERVER_CONFIG.log_waiting_period, queue=log_queue,
                            log=ActivityLog(logged_by=LogAuthor.FILE_HANDLER.value,
                                            log_category=LogType.DATABASE.value,
                                            log_details=format_exception_only(e)[0],
                                            severity=Severity.NON_CRITICAL_FAILURE.value)))
        
        raise DatabaseFailure('Failed to publicise file')
    finally:
        connection_master.reclaim_connection(proxy)

    return ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_FILE_PUBLICISE.value, ended_connection=header_component.finish), None

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
    except pg_exc.Error as e:
        asyncio.create_task(
                enqueue_log(waiting_period=SERVER_CONFIG.log_waiting_period, queue=log_queue,
                            log=ActivityLog(logged_by=LogAuthor.FILE_HANDLER.value,
                                            log_category=LogType.DATABASE.value,
                                            log_details=format_exception_only(e)[0],
                                            severity=Severity.NON_CRITICAL_FAILURE.value)))
        
        raise DatabaseFailure('Failed to hide file')
    finally:
        connection_master.reclaim_connection(proxy)

    return ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_FILE_HIDE.value, ended_connection=header_component.finish), ResponseBody(contents=orjson.dumps({'revoked_grantee_info' : revoked_grantees}))

async def grant_permission(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, permission_component: BasePermissionComponent) -> tuple[ResponseHeader, None]:
    allowed_roles: list[role_types] = ['manager', 'owner']
    if (permission_component.permission_flags & PermissionFlags.MANAGER.value): # If request is to grant manager role to a user, then only the owner of this file is allowed
        allowed_roles.remove('manager')
    
    proxy: ConnectionProxy = await connection_master.request_connection(level=2)
    try:
        if not await check_file_permission(permission_component.subject_file, permission_component.subject_file_owner, permission_component.subject_user, check_for=allowed_roles, proxy=proxy):
            raise InsufficientPermissions
        
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute('''SELECT role, granted_by
                                 FROM file_permissions
                                 WHERE file_owner = %s AND filename = %s AND grantee = %s AND granted_until > %s
                                 FOR UPDATE NOWAIT;''',
                                 (permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user, datetime.now()))
            
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
                                 SET role = %s, granted_at = %s, granted_by = %s, granted_until = %s,
                                 WHERE file_owner = %s AND filename = %s AND grantee = %s''',
                                 (requested_role, datetime.now(), auth_component.identity, permission_component.effect_duration,
                                  permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user,))
        await proxy.commit()
    except pg_exc.LockNotAvailable:
        raise OperationContested
    except pg_exc.Error as e:
        asyncio.create_task(
                enqueue_log(waiting_period=SERVER_CONFIG.log_waiting_period, queue=log_queue,
                            log=ActivityLog(logged_by=LogAuthor.FILE_HANDLER.value,
                                            log_category=LogType.DATABASE.value,
                                            log_details=format_exception_only(e)[0],
                                            severity=Severity.NON_CRITICAL_FAILURE.value)))
        
        raise DatabaseFailure('Failed to grant permission')
    finally:
        await connection_master.reclaim_connection(proxy)
    
    return ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_GRANT, ended_connection=header_component.finish), None

async def revoke_permission(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, permission_component: BasePermissionComponent) -> tuple[ResponseHeader, ResponseBody]:
    allowed_roles: list[role_types] = ['manager', 'owner']
    if (permission_component.permission_flags & PermissionFlags.MANAGER.value): # If request is to revoke a user's manager role, then only the owner of this file is allowed
        allowed_roles.remove('manager')
    
    proxy: ConnectionProxy = await connection_master.request_connection(level=2)
    try:
        if not await check_file_permission(permission_component.subject_file, permission_component.subject_file_owner, permission_component.subject_user, check_for=allowed_roles, proxy=proxy):
            raise InsufficientPermissions
        
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute('''SELECT role, granted_by, granted_at, grantee
                                 FROM file_permissions
                                 WHERE file_owner = %s AND filename = %s AND grantee = %s AND granted_until > %s
                                 FOR UPDATE NOWAIT;''',
                                 (permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user, datetime.now(),))
            permission_mapping: dict[str, str] = await cursor.fetchone()

            if not permission_mapping:
                raise OperationalConflict(f'User {permission_component.subject_user} does not have any permission on file {permission_component.subject_file} owned by {permission_component.subject_file_owner}')
            
            # Revoking a role also follows same logic as granting one. If the role was granted by the owner, then only the owner is permitted to revoke it.
            if (permission_mapping['granted_by'] == permission_component.subject_file_owner) and (auth_component.identity != permission_component.subject_file_owner):
                raise InsufficientPermissions

            await cursor.execute('''DELETE FROM file_permissions
                                 WHERE file_owner = %s AND filename = %s AND grantee = %s''',
                                 (permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user,))
        await proxy.commit()
    except pg_exc.LockNotAvailable:
        raise OperationContested
    except pg_exc.Error as e:
        asyncio.create_task(
            enqueue_log(waiting_period=SERVER_CONFIG.log_waiting_period, queue=log_queue,
                        log=ActivityLog(logged_by=LogAuthor.FILE_HANDLER.value,
                                        log_category=LogType.DATABASE.value,
                                        log_details=format_exception_only(e)[0],
                                        severity=Severity.NON_CRITICAL_FAILURE.value)))
        
        raise DatabaseFailure('Failed to revoke permission')
    finally:
        await connection_master.reclaim_connection(proxy)
    
    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_REVOKE, ended_connection=header_component.finish),
            ResponseBody(contents=orjson.dumps({'revoked_role_data' : permission_mapping})))

async def transfer_ownership(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, permission_component: BasePermissionComponent) -> tuple[ResponseHeader, ResponseBody]:
    if auth_component.identity != permission_component.subject_file_owner:
        raise InsufficientPermissions(f'Only file owner {permission_component.subject_file_owner} is permitted to transfer ownership of file {permission_component.subject_file}')
    if permission_component.subject_file_owner == permission_component.subject_user:
        raise OperationalConflict('Cannot transfer file ownership to owner themselves, what are you trying to accomplish?')
    
    proxy: ConnectionProxy = await connection_master.request_connection(level=3)
    new_fname: str = None
    transfer_datetime_iso: str = None
    try:
        async with proxy.cursor(row_factory=dict_row) as cursor:
            # Auth component can easily be tampered to reflect same username as file owner, check against database
            if not await check_file_permission(permission_component.subject_file, permission_component.subject_file_owner, permission_component.subject_user, ['owner'], proxy):
                # TODO: Log tampered identity claim in auth component
                raise InsufficientPermissions(f'Only file owner {permission_component.subject_file_owner} is permitted to transfer ownership of file {permission_component.subject_file}')
            
            # Proceed to transfer ownership 
            await cursor.execute('''SELECT *
                                 FROM file_permissions
                                 WHERE file_owner = %s
                                 FOR UPDATE NOWAIT;''',
                                 (permission_component.subject_file_owner,))
            
            # file_permissions_mapping: list[dict[str, str]] = await cursor.fetchall()  # Do we even need to return this?
            # Before committing, it is important to move this file to the new owner's directory. This way in case of an OSError/PermissionError we won't have inconsistent state
            new_fname = await asyncio.wait_for(
                asyncio.to_thread(transfer_file,
                                  root=SERVER_CONFIG.root_directory, file=permission_component.subject_file,
                                  previous_owner=permission_component.subject_file_owner, new_owner=permission_component.subject_user,
                                  deleted_cache=delete_cache, read_cache=read_cache, write_cache=write_cache, append_cache=append_cache),
                timeout=SERVER_CONFIG.file_transfer_timeout)
            if not new_fname:   # Failed to transfer file
                raise FileConflict(f'Failed to perform file transfer from {permission_component.subject_file_owner} to {permission_component.subject_user}')
            
            # It is important to rely on returned filename from transfer_file, because the new owner may have a file with the same name already in their directory. 
            # In such cases, a new filename is determined by prefixing the file with a UUID. Hence, filename must also be updated
            await cursor.execute('''UPDATE file_permissions
                                  SET file_owner = %s, filename = %s
                                  WHERE file_owner = %s AND filename = %s;''',
                                  (permission_component.subject_user, new_fname, permission_component.subject_file_owner, permission_component.subject_file,))

            await cursor.execute('''UPDATE files
                                 SET filename = %s, owner = %s
                                 WHERE filename = %s AND owner = %s;''',
                                 (new_fname, permission_component.subject_user, permission_component.subject_file_owner, permission_component.subject_user,))
        await proxy.commit()
        transfer_datetime_iso = datetime.now().isoformat()
    except Exception as e:
        # Before re-raising the same exception or a new corresponding ProtocolException, we need to rollback any file changes
        if new_fname:   # new_fname being not None implies the file was transferred, but an error occured at the database level
            await asyncio.wait_for(
                asyncio.to_thread(transfer_file,
                                  root=SERVER_CONFIG.root_directory, file=new_fname, new_name=permission_component.subject_file,
                                  previous_owner=permission_component.subject_user, new_owner=permission_component.subject_file_owner,
                                  deleted_cache=delete_cache, read_cache=read_cache, write_cache=write_cache, append_cache=append_cache),
                timeout=SERVER_CONFIG.file_transfer_timeout)
            
        if isinstance(e, pg_exc.LockNotAvailable):
            raise OperationContested
        elif isinstance(e, pg_exc.Error):
            asyncio.create_task(
                enqueue_log(waiting_period=SERVER_CONFIG.log_waiting_period, queue=log_queue,
                            log=ActivityLog(logged_by=LogAuthor.FILE_HANDLER.value,
                                            log_category=LogType.DATABASE.value,
                                            log_details=format_exception_only(e)[0],
                                            severity=Severity.NON_CRITICAL_FAILURE.value)))
            
            raise DatabaseFailure(f'Failed to transfer ownership of file {permission_component.subject_file} to {permission_component.subject_user}')
        raise e
    finally:
        await connection_master.reclaim_connection(proxy)

    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_OWNERSHIP_TRANSFER, ended_connection=header_component.finish),
            ResponseBody(contents=orjson.dumps({'old_filepath' : os.path.join(permission_component.subject_file_owner, permission_component.subject_file),
                                                'new_filepath' : os.path.join(permission_component.subject_user, new_fname),
                                                'transfer_datetime' : transfer_datetime_iso})))

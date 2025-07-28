import asyncio
from datetime import datetime
import os
import time
from typing import Any, Optional, Literal, Union
from traceback import format_exception_only

from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncIndirectBufferedIOBase

from cachetools import TTLCache

from models.flags import PermissionFlags
from models.permissions import ROLE_MAPPING
from models.permissions import RoleTypes, FilePermissions
from models.response_models import ResponseHeader, ResponseBody
from models.response_codes import SuccessFlags
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BasePermissionComponent

import psycopg.errors as pg_exc
from psycopg.rows import dict_row

from server import errors
from server import logging
from server.config import server_config
from server.connectionpool import ConnectionProxy, ConnectionPoolManager
from server.database import models as db_models
from server.file_ops import base_operations as base_ops

__all__ = ('check_file_permission', 'publicise_file', 'hide_file', 'grant_permission', 'revoke_permission', 'transfer_ownership')

async def check_file_permission(filename: str, owner: str, grantee: str, check_for: FilePermissions, connection_master: ConnectionPoolManager, proxy: Optional[ConnectionProxy] = None, level: Optional[Literal[1,2,3]] = 1, check_until: Optional[datetime] = None) -> bool:
    reclaim_after: bool = proxy is None
    if not proxy:
        proxy: ConnectionProxy = await connection_master.request_connection(level=level)
    try:
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute('''SELECT roles.permission
                                 FROM file_permissions fp
                                 INNER JOIN roles
                                 ON roles.role = fp.role
                                 WHERE fp.file_owner = %s AND fp.filename = %s AND fp.grantee = %s AND (fp.granted_until > %s OR fp.granted_until IS NULL)
                                 AND roles.permission = %s;''',
                                 (owner, filename, grantee, check_until or datetime.now(), check_for,))
            role_mapping: dict[str, FilePermissions] = await cursor.fetchone()
    finally:
        if reclaim_after:
            await connection_master.reclaim_connection(proxy)
    
    if not role_mapping:
        return False
    return True

async def publicise_file(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, permission_component: BasePermissionComponent,
                         config: server_config.ServerConfig, log_queue: asyncio.PriorityQueue[tuple[db_models.ActivityLog, int]],
                         connection_master: ConnectionPoolManager) -> tuple[ResponseHeader, None]:
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
                raise errors.FileNotFound(file=permission_component.subject_file, username=auth_component.identity)
            if result['public']:   # File already public
                raise errors.FileConflict(file=permission_component.subject_file, username=auth_component.identity)
            
            await cursor.execute('''UPDATE files
                                 SET public = TRUE
                                 WHERE owner = %s AND filename = %s;''',
                                 (auth_component.identity, permission_component.subject_file,))
        await proxy.commit()
    except pg_exc.LockNotAvailable:
        raise errors.OperationContested
    except pg_exc.Error as e:
        asyncio.create_task(
                logging.enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                                    log=db_models.ActivityLog(logged_by=db_models.LogAuthor.FILE_HANDLER,
                                            log_category=db_models.LogType.DATABASE,
                                            log_details=format_exception_only(e)[0],
                                            reported_severity=db_models.Seveirty.NON_CRITICAL_FAILURE)))
        
        raise errors.DatabaseFailure('Failed to publicise file')
    finally:
        connection_master.reclaim_connection(proxy)

    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_FILE_PUBLICISE.value, ended_connection=header_component.finish),
            None)

async def hide_file(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, permission_component: BasePermissionComponent,
                    config: server_config.ServerConfig, log_queue: asyncio.PriorityQueue[tuple[db_models.ActivityLog, int]],
                    connection_master: ConnectionPoolManager) -> tuple[ResponseHeader, ResponseBody]:
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
                raise errors.FileNotFound(file=permission_component.subject_file, username=auth_component.identity)

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
        raise errors.OperationContested
    except pg_exc.Error as e:
        asyncio.create_task(
                logging.enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                            log=db_models.ActivityLog(logged_by=db_models.LogAuthor.FILE_HANDLER,
                                            log_category=db_models.LogType.DATABASE,
                                            log_details=format_exception_only(e)[0],
                                            reported_severity=db_models.Seveirty.NON_CRITICAL_FAILURE)))
        
        raise errors.DatabaseFailure('Failed to hide file')
    finally:
        connection_master.reclaim_connection(proxy)

    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_FILE_HIDE.value, ended_connection=header_component.finish),
            ResponseBody(contents={'revoked_grantee_info' : revoked_grantees}))

async def grant_permission(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, permission_component: BasePermissionComponent,
                           config: server_config.ServerConfig, log_queue: asyncio.PriorityQueue[tuple[db_models.ActivityLog, int]],
                           connection_master: ConnectionPoolManager) -> tuple[ResponseHeader, None]:
    allowed_permission: FilePermissions = FilePermissions.MANAGE_RW
    if (permission_component.permission_flags & PermissionFlags.MANAGER.value): # If request is to grant manager role to a user, then only the owner of this file is allowed
        allowed_permission = FilePermissions.MANAGE_SUPER
    
    proxy: ConnectionProxy = await connection_master.request_connection(level=2)
    try:
        if not await check_file_permission(permission_component.subject_file, permission_component.subject_file_owner, permission_component.subject_user, check_for=allowed_permission.value, check_until=datetime.fromtimestamp(header_component.sender_timestamp) , proxy=proxy):
            raise errors.InsufficientPermissions
        
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute('''SELECT role, granted_by
                                 FROM file_permissions
                                 WHERE file_owner = %s AND filename = %s AND grantee = %s AND granted_until > %s
                                 FOR UPDATE NOWAIT;''',
                                 (permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user, datetime.now()))
            
            permission_mapping: dict[str, str] = await cursor.fetchone()
            # Extract the grantee's role
            requested_role: RoleTypes = ROLE_MAPPING[PermissionFlags._value2member_map_[permission_component.permission_flags & PermissionFlags.ROLE_EXTRACTION_BITMASK.value]]

            granted_until: datetime = None if not permission_component.effect_duration else datetime.fromtimestamp(time.time() + permission_component.effect_duration)
            if permission_mapping:
                if requested_role.value == permission_mapping['role']:
                    raise errors.OperationalConflict(f'User {permission_component.subject_user} already has permission {requested_role} on file {permission_component.subject_file} owned by {permission_component.subject_file_owner}')
                
                # Overriding a role must require new granter to have same or higher permissions than previous granter.
                # Manager -> manager overrides, including overriding an ex-manager is allowed so no checks needed.
                # However, if file owner is the granter, then only the owner themselves are allowed   
                elif (permission_mapping['granted_by'] == permission_component.subject_file_owner) and (auth_component.identity != permission_component.subject_file_owner):
                    raise errors.InsufficientPermissions(f'Insufficient permission to override role of user {permission_component.subject_user} on file {permission_component.subject_file} owned by {permission_component.subject_file_owner} (role previosuly granted by {permission_component["granted_by"]})')
                await cursor.execute('''UPDATE file_permissions
                                    SET role = %s, granted_at = %s, granted_by = %s, granted_until = %s,
                                    WHERE file_owner = %s AND filename = %s AND grantee = %s''',
                                    (requested_role, datetime.now(), auth_component.identity, granted_until,
                                    permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user,))
            else:
                # Adding a new role
                await cursor.execute('''INSERT INTO file_permissions (file_owner, filename, grantee, role, granted_at, granted_by, granted_until)
                                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s);''',
                                     (permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user,
                                      datetime.fromtimestamp(header_component.sender_timestamp), auth_component.identity, granted_until))
        
        await proxy.commit()
    except pg_exc.LockNotAvailable:
        raise errors.OperationContested
    except pg_exc.Error as e:
        asyncio.create_task(
                logging.enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                                    log=db_models.ActivityLog(logged_by=db_models.LogAuthor.FILE_HANDLER,
                                                              log_category=db_models.LogType.DATABASE,
                                                              log_details=format_exception_only(e)[0],
                                                              reported_severity=db_models.Seveirty.NON_CRITICAL_FAILURE)))
        
        raise errors.DatabaseFailure('Failed to grant permission')
    finally:
        await connection_master.reclaim_connection(proxy)
    
    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_GRANT, ended_connection=header_component.finish),
            None)

async def revoke_permission(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, permission_component: BasePermissionComponent,
                            config: server_config.ServerConfig, log_queue: asyncio.PriorityQueue[tuple[db_models.ActivityLog, int]],
                            connection_master: ConnectionPoolManager) -> tuple[ResponseHeader, ResponseBody]:
    allowed_permission: FilePermissions = FilePermissions.MANAGE_RW
    if (permission_component.permission_flags & PermissionFlags.MANAGER.value): # If request is to revoke a user's manager role, then only the owner of this file is allowed
        allowed_permission = FilePermissions.MANAGE_SUPER
    
    proxy: ConnectionProxy = await connection_master.request_connection(level=2)
    try:
        if not await check_file_permission(permission_component.subject_file, permission_component.subject_file_owner, permission_component.subject_user,
                                           check_for=allowed_permission, check_until=datetime.fromtimestamp(header_component.sender_timestamp) , proxy=proxy):
            raise errors.InsufficientPermissions
        
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute('''SELECT role, granted_by, granted_at, grantee
                                 FROM file_permissions
                                 WHERE file_owner = %s AND filename = %s AND grantee = %s AND granted_until > %s
                                 FOR UPDATE NOWAIT;''',
                                 (permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user, datetime.now(),))
            permission_mapping: dict[str, str] = await cursor.fetchone()

            if not permission_mapping:
                raise errors.OperationalConflict(f'User {permission_component.subject_user} does not have any permission on file {permission_component.subject_file} owned by {permission_component.subject_file_owner}')
            
            # Revoking a role also follows same logic as granting one. If the role was granted by the owner, then only the owner is permitted to revoke it.
            if (permission_mapping['granted_by'] == permission_component.subject_file_owner) and (auth_component.identity != permission_component.subject_file_owner):
                raise errors.InsufficientPermissions

            await cursor.execute('''DELETE FROM file_permissions
                                 WHERE file_owner = %s AND filename = %s AND grantee = %s''',
                                 (permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user,))
        await proxy.commit()
    except pg_exc.LockNotAvailable:
        raise errors.OperationContested
    except pg_exc.Error as e:
        asyncio.create_task(
            logging.enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                                log=db_models.ActivityLog(logged_by=db_models.LogAuthor.FILE_HANDLER,
                                                          log_category=db_models.LogType.DATABASE,
                                                          log_details=format_exception_only(e)[0],
                                                          reported_severity=db_models.Seveirty.NON_CRITICAL_FAILURE)))
        
        raise errors.DatabaseFailure('Failed to revoke permission')
    finally:
        await connection_master.reclaim_connection(proxy)
    
    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_REVOKE, ended_connection=header_component.finish),
            ResponseBody(contents={'revoked_role_data' : permission_mapping}))

async def transfer_ownership(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, permission_component: BasePermissionComponent,
                             config: server_config.ServerConfig, log_queue: asyncio.PriorityQueue[db_models.ActivityLog, int],
                             connection_master: ConnectionPoolManager,
                             deleted_cache: TTLCache[str, True], **cache_mapping: TTLCache[str, Union[AsyncIndirectBufferedIOBase, AsyncBufferedReader]]) -> tuple[ResponseHeader, ResponseBody]:
    if auth_component.identity != permission_component.subject_file_owner:
        raise errors.InsufficientPermissions(f'Only file owner {permission_component.subject_file_owner} is permitted to transfer ownership of file {permission_component.subject_file}')
    if permission_component.subject_file_owner == permission_component.subject_user:
        raise errors.OperationalConflict('Cannot transfer file ownership to owner themselves, what are you trying to accomplish?')
    
    proxy: ConnectionProxy = await connection_master.request_connection(level=3)
    new_fname: str = None
    transfer_datetime_iso: str = None
    try:
        async with proxy.cursor(row_factory=dict_row) as cursor:
            # Auth component can easily be tampered to reflect same username as file owner, check against database
            if not await check_file_permission(permission_component.subject_file, permission_component.subject_file_owner, permission_component.subject_user, ['owner'], proxy):
                # TODO: Log tampered identity claim in auth component
                raise errors.InsufficientPermissions(f'Only file owner {permission_component.subject_file_owner} is permitted to transfer ownership of file {permission_component.subject_file}')
            
            # Proceed to transfer ownership 
            await cursor.execute('''SELECT *
                                 FROM file_permissions
                                 WHERE file_owner = %s
                                 FOR UPDATE NOWAIT;''',
                                 (permission_component.subject_file_owner,))
            
            # file_permissions_mapping: list[dict[str, str]] = await cursor.fetchall()  # Do we even need to return this?
            # Before committing, it is important to move this file to the new owner's directory. This way in case of an OSError/PermissionError we won't have inconsistent state
            new_fname = await asyncio.wait_for(
                asyncio.to_thread(base_ops.transfer_file,
                                  root=config.root_directory, file=permission_component.subject_file,
                                  previous_owner=permission_component.subject_file_owner, new_owner=permission_component.subject_user,
                                  deleted_cache=deleted_cache, **cache_mapping),
                timeout=config.file_transfer_timeout)
            if not new_fname:   # Failed to transfer file
                raise errors.FileConflict(f'Failed to perform file transfer from {permission_component.subject_file_owner} to {permission_component.subject_user}')
            
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
                asyncio.to_thread(base_ops.transfer_file,
                                  root=config.root_directory, file=new_fname, new_name=permission_component.subject_file,
                                  previous_owner=permission_component.subject_user, new_owner=permission_component.subject_file_owner,
                                  deleted_cache=deleted_cache, **cache_mapping),
                timeout=config.file_transfer_timeout)
            
        if isinstance(e, pg_exc.LockNotAvailable):
            raise errors.OperationContested
        elif isinstance(e, pg_exc.Error):
            asyncio.create_task(
                logging.enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                            log=db_models.ActivityLog(logged_by=db_models.LogAuthor.FILE_HANDLER,
                                            log_category=db_models.LogType.DATABASE,
                                            log_details=format_exception_only(e)[0],
                                            reported_severity=db_models.Seveirty.NON_CRITICAL_FAILURE)))
            
            raise errors.DatabaseFailure(f'Failed to transfer ownership of file {permission_component.subject_file} to {permission_component.subject_user}')
        raise e
    finally:
        await connection_master.reclaim_connection(proxy)

    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_OWNERSHIP_TRANSFER, ended_connection=header_component.finish),
            ResponseBody(contents={'old_filepath' : os.path.join(permission_component.subject_file_owner, permission_component.subject_file),
                                   'new_filepath' : os.path.join(permission_component.subject_user, new_fname),
                                   'transfer_datetime' : transfer_datetime_iso}))

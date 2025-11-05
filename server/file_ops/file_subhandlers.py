import asyncio
import os
from datetime import datetime
from typing import Any
from typing import Final

import psycopg

from models.cursor_flag import CursorFlag
from models.flags import FileFlags
from models.response_models import ResponseHeader, ResponseBody
from models.response_codes import SuccessFlags
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BaseFileComponent
from models.permissions import RoleTypes, FilePermissions

from psycopg.rows import dict_row

from server.config import server_config
from server.database.connections import ConnectionPoolManager
from server.database import models as db_models, utils as db_utils
from server.file_ops import base_operations as base_ops
from server.file_ops import cache_ops
from server import errors
from server.logging import enqueue_log
from server.dependencies import GlobalLogQueueType, GlobalFileLockType, GlobalDeleteCacheType, GlobalReadCacheType, GlobalAmendCacheType
from server.file_ops.storage import StorageCache
from server.file_ops.utils import check_amendmend_storage_integrity

__all__ = ('handle_deletion', 'handle_amendment', 'handle_read', 'handle_creation')

async def handle_deletion(header_component: BaseHeaderComponent,
                          auth_component: BaseAuthComponent,
                          file_component: BaseFileComponent,
                          config: server_config.ServerConfig,
                          log_queue: GlobalLogQueueType,
                          connection_master: ConnectionPoolManager,
                          file_locks: GlobalFileLockType,
                          deleted_cache: GlobalDeleteCacheType,
                          read_cache: GlobalReadCacheType,
                          amendment_cache: GlobalAmendCacheType,
                          storage_cache: StorageCache) -> tuple[ResponseHeader, ResponseBody]:
    # Make sure request is coming from file owner
    if file_component.subject_file_owner != auth_component.identity:
        err_str: str = f'Missing permission to delete file {file_component.subject_file} owned by {file_component.subject_file_owner}'
        asyncio.create_task(
            enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                        log=db_models.ActivityLog(logged_by=db_models.LogAuthor.FILE_HANDLER,
                                                  log_category=db_models.LogType.PERMISSION,
                                                  log_details=err_str,
                                                  reported_severity=db_models.Severity.TRACE,
                                                  user_concerned=auth_component.identity)))
        
        raise errors.InsufficientPermissions(err_str)
    
    # Request validated. No need to acquire lock since owner's deletion request is more important than any concurrent file amendment locks
    file: Final[str] = os.path.join(file_component.subject_file_owner, file_component.subject_file)
    file_locks[file] = auth_component.identity  # Overwrite any active amendment locks with the owner's lock
    revoked_info: list[dict[str, Any]] = []
    
    async with await connection_master.request_connection(level=3) as proxy:
        file_size: int = await storage_cache.get_file_size(auth_component.identity, file_component.subject_file, proxy, release_after=False)   # Prefetch file size
        async with proxy.cursor(row_factory=dict_row) as cursor:
            try:
                await cursor.execute('''SELECT * FROM files
                                     WHERE filename = %s AND owner = %s
                                     FOR UPDATE NOWAIT;''',
                                     (file_component.subject_file, auth_component.identity))
                await cursor.fetchall() # Flush selection from buffer

                await cursor.execute('''SELECT * FROM FILE_PERMISSIONS
                                    WHERE file_owner = %s AND filename = %s
                                    FOR UPDATE NOWAIT;''',
                                    (auth_component.identity, file_component.subject_file))
                revoked_info = await cursor.fetchall()

                await cursor.execute('''DELETE FROM files
                                     WHERE filename = %s AND owner = %s;''',
                                    (file_component.subject_file, auth_component.identity,))
                
                file_deleted: bool = await base_ops.delete_file(config.files_directory, file,
                                                                deleted_cache, read_cache, amendment_cache) 
                if not file_deleted:
                    err_str: str = f'Failed to delete file {file_component.subject_file}'
                    asyncio.create_task(
                        enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                                    log=db_models.ActivityLog(logged_by=db_models.LogAuthor.FILE_HANDLER,
                                                              log_category=db_models.LogType.INTERNAL,
                                                              log_details=err_str,
                                                              reported_severity=db_models.Severity.NON_CRITICAL_FAILURE,
                                                              user_concerned=auth_component.identity)))
                    
                    raise errors.InsufficientPermissions(err_str)
                
                await proxy.commit()
                await storage_cache.reflect_removed_file(auth_component.identity, file_size, proxy)
            except psycopg.errors.Error as exception:
                raise errors.DatabaseFailure(f"Failed to delete file {file}")

    file_locks.pop(file)
    
    deletion_time: datetime = datetime.now()
    asyncio.create_task(
        enqueue_log(queue=log_queue, waiting_period=config.log_waiting_period,
                    log=db_models.ActivityLog(occurance_time=deletion_time,
                                              reported_severity=db_models.Severity.INFO,
                                              logged_by=db_models.LogAuthor.FILE_HANDLER,
                                              log_category=db_models.LogType.REQUEST,
                                              user_concerned=auth_component.identity)))
    
    return (ResponseHeader.from_server(version=header_component.version,
                                       code=SuccessFlags.SUCCESSFUL_FILE_DELETION,
                                       ended_connection=header_component.finish,
                                       config=config),
            ResponseBody(contents={'revoked_info' : revoked_info, 'deletion_time' : deletion_time.isoformat()}))

async def handle_amendment(header_component: BaseHeaderComponent,
                           auth_component: BaseAuthComponent,
                           file_component: BaseFileComponent,
                           config: server_config.ServerConfig,
                           log_queue: GlobalLogQueueType,
                           file_locks: GlobalFileLockType,
                           connection_master: ConnectionPoolManager,
                           delete_cache: GlobalDeleteCacheType,
                           amendment_cache: GlobalAmendCacheType,
                           storage_cache: StorageCache) -> tuple[ResponseHeader, ResponseBody]:
    if not file_component.write_data:
        raise errors.InvalidFileData("Missing write data for file amendment")
    
    async with await connection_master.request_connection(1) as proxy:
        if not await db_utils.check_file_existence(filename=file_component.subject_file,
                                                   owner=file_component.subject_file_owner,
                                                   connection_master=connection_master,
                                                   proxy=proxy):
            raise errors.FileNotFound(file=file_component.subject_file, username=file_component.subject_file_owner)
        
        if not await db_utils.check_file_permission(filename=file_component.subject_file,
                                                    owner=file_component.subject_file_owner,
                                                    grantee=auth_component.identity,
                                                    connection_master=connection_master,
                                                    proxy=proxy,
                                                    check_for=FilePermissions.WRITE,
                                                    check_until=datetime.fromtimestamp(header_component.sender_timestamp)):
            err_str: str = f'User {auth_component.identity} does not have write permission on file {file_component.subject_file} owned by {file_component.subject_file_owner}'
            asyncio.create_task(
                enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                            log=db_models.ActivityLog(logged_by=db_models.LogAuthor.FILE_HANDLER,
                                                    log_category=db_models.LogType.PERMISSION,
                                                    log_details=err_str,
                                                    reported_severity=db_models.Severity.TRACE,
                                                    user_concerned=auth_component.identity)))
            
            raise errors.InsufficientPermissions(err_str)
    
        current_storage_used: int = (await storage_cache.get_storage_data(auth_component.identity, proxy=proxy)).storage_used
        file_size: int = await storage_cache.get_file_size(username=file_component.subject_file_owner, file=file_component.subject_file)
        if not check_amendmend_storage_integrity(content_size=len(file_component.write_data),
                                                 current_file_size=file_size,
                                                 current_storage_used=current_storage_used,
                                                 server_config=config,
                                                 is_append=bool(header_component.subcategory & FileFlags.APPEND)):
            err_str: str = f'Insufficient storage for amendment on file {file_component.relative_pathlike}, current storage: {current_storage_used}'
            asyncio.create_task(
                enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                            log=db_models.ActivityLog(logged_by=db_models.LogAuthor.FILE_HANDLER,
                                                    log_category=db_models.LogType.PERMISSION,
                                                    log_details=err_str,
                                                    reported_severity=db_models.Severity.TRACE,
                                                    user_concerned=auth_component.identity)))
            
            raise errors.FileConflict(file=file_component.subject_file, username=file_component.subject_file_owner)

    fpath: Final[str] = os.path.join(file_component.subject_file_owner, file_component.subject_file)
    if file_component.subject_file_owner == auth_component.identity:
        file_locks[fpath] = auth_component.identity
    else:
        try:
            await asyncio.wait_for(base_ops.acquire_file_lock(file_locks=file_locks, filename=fpath, requestor=auth_component.identity),
                                timeout=config.file_contention_timeout)
        except asyncio.TimeoutError:
            raise errors.FileContested(file=file_component.subject_file, username=file_component.subject_file_owner)

    if header_component.subcategory & (FileFlags.WRITE | FileFlags.OVERWRITE):
        cursor_position = await base_ops.write_file(root=config.files_directory, fpath=fpath,
                                                    data=file_component.write_data,
                                                    deleted_cache=delete_cache, amendment_cache=amendment_cache,
                                                    cursor_position=file_component.cursor_position or 0,
                                                    writer_keepalive=bool(file_component.cursor_bitfield & CursorFlag.CURSOR_KEEPALIVE),
                                                    purge_writer=file_component.end_operation or bool(file_component.cursor_bitfield & CursorFlag.PURGE_CURSOR),
                                                    identifier=auth_component.identity,
                                                    trunacate=bool(header_component.subcategory & FileFlags.OVERWRITE))
        await storage_cache.update_file_size(file_component.subject_file,
                                             diff=(
                                                 (cursor_position - file_size) if (header_component.subcategory & FileFlags.OVERWRITE)
                                                 else max(0, cursor_position - file_size)
                                            ))
    else:
        cursor_position = await base_ops.append_file(root=config.files_directory, fpath=fpath,
                                                     data=file_component.write_data,
                                                     deleted_cache=delete_cache, amendment_cache=amendment_cache,
                                                     append_writer_keepalive=bool(file_component.cursor_bitfield & CursorFlag.CURSOR_KEEPALIVE),
                                                     purge_append_writer=file_component.end_operation or bool(file_component.cursor_bitfield & CursorFlag.PURGE_CURSOR),
                                                     identifier=auth_component.identity)
        await storage_cache.update_file_size(file_component.subject_file_owner,
                                             diff=cursor_position - file_size)
    
    keepalive_accepted = cache_ops.get_buffer(amendment_cache, fpath, auth_component.identity)
    if not keepalive_accepted:
        file_locks.pop(fpath)
    
    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_AMEND, ended_connection=header_component.finish, config=config),
            ResponseBody(cursor_position=cursor_position, cursor_keepalive_accepted=bool(keepalive_accepted)))

async def handle_read(header_component: BaseHeaderComponent,
                      auth_component: BaseAuthComponent,
                      file_component: BaseFileComponent,
                      config: server_config.ServerConfig,
                      log_queue: GlobalLogQueueType,
                      connection_master: ConnectionPoolManager,
                      file_locks: GlobalFileLockType,
                      delete_cache: GlobalDeleteCacheType,
                      read_cache: GlobalReadCacheType) -> tuple[ResponseHeader, ResponseBody]:    
    # Check permissions
    if not await db_utils.check_file_permission(filename=file_component.subject_file,
                                                owner=file_component.subject_file_owner,
                                                grantee=auth_component.identity,
                                                connection_master=connection_master,
                                                check_for=FilePermissions.READ,
                                                check_until=datetime.fromtimestamp(header_component.sender_timestamp)):
        err_str: str = f'User {auth_component.identity} does not have read permission on file {file_component.subject_file} owned by {file_component.subject_file_owner}'
        asyncio.create_task(
            enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                        log=db_models.ActivityLog(logged_by=db_models.LogAuthor.FILE_HANDLER,
                                                  log_category=db_models.LogType.PERMISSION,log_details=err_str,
                                                  reported_severity=db_models.Severity.TRACE,
                                                  user_concerned=auth_component.identity)))
        
        raise errors.InsufficientPermissions(err_str)
    
    fpath: Final[str] = os.path.join(file_component.subject_file_owner, file_component.subject_file)
    read_data, cursor_position, eof_reached = await base_ops.read_file(root=config.files_directory, fpath=fpath,
                                                                       deleted_cache=delete_cache, read_cache=read_cache,
                                                                       cursor_position=file_component.cursor_position or 0,
                                                                       nbytes=file_component.chunk_size,
                                                                       reader_keepalive=bool(file_component.cursor_bitfield & CursorFlag.CURSOR_KEEPALIVE),
                                                                       identifier=auth_component.identity)
    
    ongoing_amendment: bool = bool(file_locks.get(fpath))
    if (cursor_killed:=eof_reached and not (file_component.cursor_bitfield & CursorFlag.CURSOR_KEEPALIVE)):
        cache_ops.remove_buffer(read_cache, fpath, auth_component.identity)

    return (ResponseHeader.from_server(config=config,
                                       version=header_component.version,
                                       code=SuccessFlags.SUCCESSFUL_READ,
                                       ended_connection=header_component.finish),
            ResponseBody(contents={'read' : read_data, 'ongoing_amendment' : ongoing_amendment},
                         operation_ended=eof_reached,
                         cursor_position=cursor_position,
                         cursor_keepalive_accepted=not cursor_killed))

async def handle_creation(header_component: BaseHeaderComponent,
                          auth_component: BaseAuthComponent,
                          file_component: BaseFileComponent,
                          config: server_config.ServerConfig,
                          log_queue: GlobalLogQueueType,
                          connection_master: ConnectionPoolManager,
                          deletion_cache: GlobalDeleteCacheType,
                          storage_cache: StorageCache) -> tuple[ResponseHeader, ResponseBody]:
    if file_component.subject_file_owner != auth_component.identity:
        asyncio.create_task(
            enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                        log=db_models.ActivityLog(logged_by=db_models.LogAuthor.FILE_HANDLER,
                                                  log_category=db_models.LogType.PERMISSION,
                                                  log_details=f'User {auth_component.identity} attempted to create files in /{file_component.subject_file_owner}',
                                                  reported_severity=db_models.Severity.TRACE)))
        
        raise errors.InvalidFileData(f'As user {auth_component.identity}, you only have permission to create new files in your own directory and not /{file_component.subject_file_owner}')
    if (await storage_cache.get_storage_data(auth_component.identity)).filecount >= config.user_max_files:
        raise errors.FileOperationForbidden(filecount_exceeded=True)
    
    fpath, epoch = await base_ops.create_file(root=config.files_directory, owner=auth_component.identity, filename=file_component.subject_file)

    if fpath:
        assert epoch
        # Add record for this file
        async with await connection_master.request_connection(level=3) as proxy:
            try:
                await proxy.execute('''INSERT INTO files (filename, owner, created_at)
                                    VALUES (%s, %s, %s);''',
                                    (file_component.subject_file, auth_component.identity, datetime.fromtimestamp(epoch), ))
                await proxy.execute('''INSERT INTO file_permissions (file_owner, filename, grantee, role, granted_by, granted_at)
                                    VALUES (%s, %s, %s, %s, %s, %s);''',
                                    (auth_component.identity, file_component.subject_file, auth_component.identity,
                                    RoleTypes.OWNER.value, auth_component.identity, datetime.fromtimestamp(header_component.sender_timestamp),))
                await proxy.commit()

                new_filecount: int = await storage_cache.update_file_count(auth_component.identity, file_component.subject_file, proxy=proxy)
                if new_filecount > config.user_max_files:
                    await base_ops.delete_file(root=config.files_directory, fpath=fpath, deleted_cache=deletion_cache)
                    raise errors.FileOperationForbidden(filecount_exceeded=True)
                
                await proxy.commit()
            except psycopg.errors.Error:
                await base_ops.delete_file(config.files_directory, file_component.subject_file, deletion_cache)
                raise errors.DatabaseFailure(f"Failed to register new file {file_component.subject_file}")
    else:
        asyncio.create_task(enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                                        log=db_models.ActivityLog(logged_by=db_models.LogAuthor.FILE_HANDLER,
                                                        log_category=db_models.LogType.INTERNAL,
                                                        log_details=f'Failed to create file {fpath}',
                                                        reported_severity=db_models.Severity.TRACE,
                                                        user_concerned=auth_component.identity)))
        
        raise errors.FileConflict(file_component.subject_file, username=auth_component.identity)
    
    return (ResponseHeader.from_server(version=header_component.version,
                                       code=SuccessFlags.SUCCESSFUL_FILE_CREATION,
                                       ended_connection=header_component.finish,
                                       config=config),
            ResponseBody(operation_ended=True,
                         cursor_keepalive_accepted=False,
                         contents={'path' : fpath, 'iso_epoch' : datetime.fromtimestamp(epoch).isoformat()}))

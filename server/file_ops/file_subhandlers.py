import asyncio
import os
from datetime import datetime
from typing import Any
from zlib import adler32

from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncBufferedIOBase

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

from cachetools import TTLCache

__all__ = ('handle_deletion', 'handle_amendment', 'handle_read', 'handle_creation')

async def handle_deletion(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, file_component: BaseFileComponent,
                          config: server_config.ServerConfig, log_queue: asyncio.Queue[db_models.ActivityLog],
                          connection_master: ConnectionPoolManager, file_locks: TTLCache[str, bytes],
                          deleted_cache: TTLCache[str, str],
                          read_cache: TTLCache[str, dict[str, AsyncBufferedReader]],
                          amendment_cache: TTLCache[str, dict[str, AsyncBufferedReader]]) -> tuple[ResponseHeader, ResponseBody]:
    # Make sure request is coming from file owner
    if file_component.subject_file_owner != auth_component.identity:
        err_str: str = f'Missing permission to delete file {file_component.subject_file} owned by {file_component.subject_file_owner}'
        asyncio.create_task(
            enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                        log=db_models.db_models.ActivityLog(logged_by=db_models.db_models.LogAuthor.FILE_HANDLER,
                                                  log_category=db_models.LogType.PERMISSION,
                                                  log_details=err_str,
                                                  reported_severity=db_models.Severity.TRACE,
                                                  user_concerned=auth_component.identity)))
        
        raise errors.InsufficientPermissions(err_str)
    
    # Request validated. No need to acquire lock since owner's deletion request is more important than any concurrent file amendment locks
    file: os.PathLike = os.path.join(file_component.subject_file_owner, file_component.subject_file)

    file_deleted: bool = await base_ops.delete_file(config.files_directory, file, deleted_cache, read_cache, amendment_cache)
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
    
    # Update database to delete all file info pertaining to this file
    file_locks[file] = None
    revoked_info: list[dict[str, Any]] = []
    async with await connection_master.request_connection(level=3) as proxy:
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute('''SELECT * FROM FILE_PERMISSIONS
                                 WHERE file_owner = %s AND filename = %s;''',
                                 (file_component.subject_file, auth_component.identity,))
            revoked_info = await cursor.fetchall()

            await cursor.execute('''DELETE FROM files
                                 WHERE filename = %s AND owner = %s;''',
                                 (file_component.subject_file, auth_component.identity,))
        await proxy.commit()
    
    deletion_time: datetime = datetime.now()
    asyncio.create_task(
        enqueue_log(queue=log_queue, waiting_period=config.log_waiting_period,
                    log=db_models.ActivityLog(occurance_time=deletion_time,
                                    reported_severity=db_models.Severity.INFO,
                                    logged_by=db_models.LogAuthor.FILE_HANDLER,
                                    log_category=db_models.LogType.REQUEST,
                                    user_concerned=auth_component.identity)))
    
    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_FILE_DELETION.value, ended_connection=header_component.finish, config=config),
            ResponseBody(contents={'revoked_info' : revoked_info, 'deletion_time' : deletion_time.isoformat()}))

async def handle_amendment(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, file_component: BaseFileComponent,
                           config: server_config.ServerConfig, log_queue: asyncio.Queue[db_models.ActivityLog],
                           file_locks: TTLCache[str, bytes], connection_master: ConnectionPoolManager,
                           delete_cache: TTLCache[str, str], 
                           amendment_cache: TTLCache[str, dict[str, AsyncBufferedIOBase]]) -> tuple[ResponseHeader, ResponseBody]:
    async with await connection_master.request_connection(1) as proxy:
        if not await db_utils.check_file_existence(filename=file_component.subject_file,
                                                   owner=file_component.subject_file_owner,
                                                   proxy=proxy):
            raise errors.FileNotFound(f'No file named {file_component.subject_file} owned by {file_component.subject_file_owner} found')
        
        if not await db_utils.check_file_permission(filename=file_component.subject_file,
                                                    owner=file_component.subject_file_owner,
                                                    grantee=auth_component.identity,
                                                    connection_master=connection_master,
                                                    proxy=proxy,
                                                    check_for=FilePermissions.WRITE.value,
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
    
    fpath: os.PathLike = os.path.join(file_component.subject_file_owner, file_component.subject_file)
    if file_component.subject_file_owner == auth_component.identity:
        file_locks[fpath] = adler32(auth_component.identity)
    else:
        try:
            await asyncio.wait_for(base_ops.acquire_file_lock(file_locks=file_locks, filename=fpath, requestor=auth_component.identity, ttl=config.file_lock_ttl),
                                timeout=config.file_contention_timeout)
        except asyncio.TimeoutError:
            raise errors.FileContested(file=file_component.subject_file, username=file_component.subject_file_owner)

    cursor_position: int = None
    keepalive_accepted: bool = False

    if header_component.subcategory & (FileFlags.WRITE | FileFlags.OVERWRITE):
        cursor_position = await base_ops.write_file(root=config.files_directory, fpath=fpath,
                                                    data=file_component.write_data,
                                                    deleted_cache=delete_cache, amendment_cache=amendment_cache,
                                                    cursor_position=file_component.cursor_position or 0,
                                                    writer_keepalive=file_component.cursor_bitfield & CursorFlag.CURSOR_KEEPALIVE,
                                                    purge_writer=file_component.end_operation or (file_component.cursor_bitfield & CursorFlag.PURGE_CURSOR),
                                                    identifier=auth_component.identity,
                                                    trunacate=header_component.subcategory & FileFlags.OVERWRITE)
    else:
        cursor_position = await base_ops.append_file(root=config.files_directory, fpath=fpath,
                                                     data=file_component.write_data,
                                                     deleted_cache=delete_cache, amendment_cache=amendment_cache,
                                                     append_writer_keepalive=file_component.cursor_bitfield & CursorFlag.CURSOR_KEEPALIVE,
                                                     purge_append_writer=file_component.end_operation or (file_component.cursor_bitfield & CursorFlag.PURGE_CURSOR),
                                                     identifier=auth_component.identity)
    
    keepalive_accepted = cache_ops.get_reader(amendment_cache, fpath, auth_component.identity)
    if not keepalive_accepted:
        file_locks.pop(fpath)
    
    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_AMEND, ended_connection=header_component.finish, config=config),
            ResponseBody(cursor_position=cursor_position, cursor_keepalive_accepted=bool(keepalive_accepted)))

async def handle_read(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, file_component: BaseFileComponent,
                      config: server_config.ServerConfig, log_queue: asyncio.Queue[db_models.ActivityLog],
                      connection_master: ConnectionPoolManager,
                      file_locks: TTLCache[str, bytes],
                      delete_cache: TTLCache[str, str],
                      read_cache: TTLCache[str, dict[str, AsyncBufferedIOBase]]) -> tuple[ResponseHeader, ResponseBody]:    
    # Check permissions
    if not await db_utils.check_file_permission(filename=file_component.subject_file,
                                                owner=file_component.subject_file_owner,
                                                grantee=auth_component.identity,
                                                connection_master=connection_master,
                                                check_for=FilePermissions.READ.value,
                                                check_until=datetime.fromtimestamp(header_component.sender_timestamp)):
        err_str: str = f'User {auth_component.identity} does not have read permission on file {file_component.subject_file} owned by {file_component.subject_file_owner}'
        asyncio.create_task(
            enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                        log=db_models.ActivityLog(logged_by=db_models.LogAuthor.FILE_HANDLER,
                                                  log_category=db_models.LogType.PERMISSION,log_details=err_str,
                                                  reported_severity=db_models.Severity.TRACE,
                                                  user_concerned=auth_component.identity)))
        
        raise errors.InsufficientPermissions(err_str)
    
    fpath: os.PathLike = os.path.join(file_component.subject_file_owner, file_component.subject_file)
    read_data, cursor_position, eof_reached = await base_ops.read_file(root=config.files_directory, fpath=fpath,
                                                                       deleted_cache=delete_cache, read_cache=read_cache,
                                                                       cursor_position=file_component.cursor_position, nbytes=file_component.chunk_size,
                                                                       reader_keepalive=file_component.cursor_bitfield & CursorFlag.CURSOR_KEEPALIVE,
                                                                       identifier=auth_component.identity)
    
    ongoing_amendment: bool = bool(file_locks.get(fpath))
    if (cursor_killed:=eof_reached and not (file_component.cursor_bitfield & CursorFlag.CURSOR_KEEPALIVE)):
        cache_ops.remove_reader(read_cache, fpath, auth_component.identity)

    return (ResponseHeader.from_server(config=config,
                                       version=header_component.version,
                                       code=SuccessFlags.SUCCESSFUL_READ,
                                       ended_connection=header_component.finish),
            ResponseBody(contents={'read' : read_data, 'ongoing_amendment' : ongoing_amendment},
                         operation_ended=eof_reached,
                         cursor_position=cursor_position,
                         keepalive_accepted=not cursor_killed))

async def handle_creation(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, file_component: BaseFileComponent,
                          config: server_config.ServerConfig, log_queue: asyncio.Queue[db_models.ActivityLog],
                          connection_master: ConnectionPoolManager
                          ) -> tuple[ResponseHeader, None]:
    if file_component.subject_file_owner != auth_component.identity:
        asyncio.create_task(
            enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                        log=db_models.ActivityLog(logged_by=db_models.LogAuthor.FILE_HANDLER,
                                                  log_category=db_models.LogType.PERMISSION,
                                                  log_details=f'User {auth_component.identity} attempted to create files in /{file_component.subject_file_owner}',
                                                  reported_severity=db_models.Severity.TRACE)))
        
        raise errors.InvalidFileData(f'As user {auth_component.identity}, you only have permission to create new files in your own directory and not /{file_component.subject_file_owner}')
    
    fpath, epoch = await base_ops.create_file(root=config.files_directory, owner=auth_component.identity, filename=file_component.subject_file)

    if fpath:
        # Add record for this file
        async with await connection_master.request_connection(level=3) as proxy:
            await proxy.execute('''INSERT INTO files (filename, owner, created_at)
                                VALUES (%s, %s, %s);''',
                                (file_component.subject_file, auth_component.identity, datetime.fromtimestamp(epoch), ))
            await proxy.execute('''INSERT INTO file_permissions (file_owner, filename, grantee, role, granted_by, granted_at)
                                VALUES (%s, %s, %s, %s, %s, %s);''',
                                (auth_component.identity, file_component.subject_file, auth_component.identity,
                                RoleTypes.OWNER.value, auth_component.identity, datetime.fromtimestamp(header_component.sender_timestamp),))
    else:
        asyncio.create_task(enqueue_log(waiting_period=config.log_waiting_period, queue=log_queue,
                                        log=db_models.ActivityLog(logged_by=db_models.LogAuthor.FILE_HANDLER,
                                                        log_category=db_models.LogType.INTERNAL,
                                                        log_details=f'Failed to create file {fpath}',
                                                        reported_severity=db_models.Severity.TRACE,
                                                        user_concerned=auth_component.identity)))
        
        raise errors.FileConflict(file_component.subject_file, username=auth_component.identity)
    
    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_FILE_CREATION.value, ended_connection=header_component.finish, config=config),
            ResponseBody(operation_ended=True, keepalive_accepted=False, contents={'path' : fpath, 'iso_epoch' : datetime.fromtimestamp(epoch).isoformat()}))
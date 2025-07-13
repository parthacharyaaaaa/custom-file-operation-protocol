import asyncio
from datetime import datetime
import os
from traceback import format_exception_only

from models.flags import FileFlags
from models.response_models import ResponseHeader, ResponseBody
from models.response_codes import SuccessFlags
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BaseFileComponent
from models.permissions import RoleTypes, FilePermissions

from psycopg.rows import dict_row

from server.bootup import file_locks, delete_cache, read_cache, write_cache, append_cache, log_queue, connection_master
from server.config.server_config import SERVER_CONFIG
from server.connectionpool import ConnectionProxy
from server.database.models import ActivityLog, LogAuthor, LogType, Severity
from server.file_ops.base_operations import create_file, read_file, write_file, append_file, delete_file, acquire_file_lock
from server.file_ops.cache_ops import get_reader
from server.errors import InsufficientPermissions, FileConflict, FileContested, InvalidFileData
from server.logging import enqueue_log
from server.permission_ops.permission_subhandlers import check_file_permission

import orjson

async def handle_deletion(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, file_component: BaseFileComponent) -> tuple[ResponseHeader, None]:
    # Make sure request is coming from file owner
    if file_component.subject_file_owner != auth_component.identity:
        err_str: str = f'Missing permission to delete file {file_component.subject_file} owned by {file_component.subject_file_owner}'
        asyncio.create_task(
            enqueue_log(waiting_period=SERVER_CONFIG.log_waiting_period, queue=log_queue,
                log=ActivityLog(logged_by=LogAuthor.FILE_HANDLER.value,
                                log_category=LogType.PERMISSION.value,
                                log_details=err_str,
                                severity=Severity.TRACE.value,
                                user_concerned=auth_component.identity)))
        
        raise InsufficientPermissions(err_str)
    
    # Request validated. No need to acquire lock since owner's deletion request is more important than any concurrent file amendment locks
    file: os.PathLike = os.path.join(file_component.subject_file_owner, file_component.subject_file)

    file_deleted: bool = await delete_file(SERVER_CONFIG.root_directory, file, delete_cache, append_cache, read_cache, write_cache)
    if not file_deleted:
        err_str: str = f'Failed to delete file {file_component.subject_file}'
        asyncio.create_task(
            enqueue_log(waiting_period=SERVER_CONFIG.log_waiting_period, queue=log_queue,
                        log=ActivityLog(logged_by=LogAuthor.FILE_HANDLER.value,
                                        log_category=LogType.INTERNAL.value,
                                        log_details=err_str,
                                        severity=Severity.NON_CRITICAL_FAILURE.value,
                                        user_concerned=auth_component.identity)))
        
        raise InsufficientPermissions(err_str)
    
    # Update database to delete all file info pertaining to this file
    file_locks[file] = None
    proxy: ConnectionProxy = await connection_master.request_connection(level=1)
    try:
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute('''DELETE FROM files
                                 WHERE filename = %s AND owner = %s;''',
                                 (file_component.subject_file, auth_component.identity,))
        await proxy.commit()
    finally:
        await connection_master.reclaim_connection(proxy)
    
    asyncio.create_task(
        enqueue_log(queue=log_queue, waiting_period=SERVER_CONFIG.log_waiting_period,
                    log=ActivityLog(severity=Severity.INFO.value,
                                    logged_by=LogAuthor.FILE_HANDLER.value,
                                    log_category=LogType.REQUEST.value,
                                    user_concerned=auth_component.identity)))
    
    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_FILE_DELETION.value, ended_connection=header_component.finish, config=SERVER_CONFIG),
            None)

async def handle_amendment(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, file_component: BaseFileComponent) -> tuple[ResponseHeader, ResponseBody]:
    # Check permissions
    if not await check_file_permission(filename=file_component.subject_file, owner=file_component.subject_file_owner, grantee=auth_component.identity,
                                       check_for=FilePermissions.WRITE.value, check_until=datetime.fromtimestamp(header_component.sender_timestamp)):
        err_str: str = f'User {auth_component.identity} does not have write permission on file {file_component.subject_file} owned by {file_component.subject_file_owner}'
        asyncio.create_task(
            enqueue_log(waiting_period=SERVER_CONFIG.log_waiting_period, queue=log_queue,
                        log=ActivityLog(logged_by=LogAuthor.FILE_HANDLER.value,
                                        log_category=LogType.PERMISSION.value,
                                        log_details=err_str,
                                        severity=Severity.TRACE.value,
                                        user_concerned=auth_component.identity)))
        
        raise InsufficientPermissions(err_str)
    
    fpath: os.PathLike = os.path.join(file_component.subject_file_owner, file_component.subject_file)
    # Acquire lock
    try:
        await asyncio.wait_for(acquire_file_lock(filename=fpath, requestor=auth_component.identity),
                               timeout=SERVER_CONFIG.file_contention_timeout)
    except asyncio.TimeoutError:
        raise FileContested(file=file_component.subject_file, username=file_component.subject_file_owner)

    cursor_position: int = None
    keepalive_accepted: bool = False

    if header_component.subcategory & FileFlags.WRITE:
        cursor_position = await write_file(root=SERVER_CONFIG.root_directory, fpath=fpath,
                                           data=file_component.write_data.encode('utf-8'),
                                           deleted_cache=delete_cache, write_cache=write_cache,
                                           cursor_position=file_component.cursor_position or 0, writer_keepalive=file_component.cursor_keepalive, purge_writer=header_component.finish,
                                           identifier=auth_component.identity, cached=True)
        keepalive_accepted = get_reader(write_cache, fpath, auth_component.identity) 
    else:
        cursor_position = await append_file(root=SERVER_CONFIG.root_directory, fpath=fpath,
                                           data=file_component.write_data.encode('utf-8'),
                                           deleted_cache=delete_cache, append_cache=append_cache,
                                           append_writer_keepalive=file_component.cursor_keepalive, purge_append_writer=header_component.finish,
                                           identifier=auth_component.identity, cached=True)
        keepalive_accepted = get_reader(append_cache, fpath, auth_component.identity) 
    
    if not keepalive_accepted:
        file_locks.pop(fpath)
    
    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_AMEND, ended_connection=header_component.finish, config=SERVER_CONFIG),
            ResponseBody(cursor_position=cursor_position, keepalive_accepted=keepalive_accepted))

async def handle_read(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, file_component: BaseFileComponent) -> tuple[ResponseHeader, ResponseBody]:    
    # Check permissions
    if not await check_file_permission(filename=file_component.subject_file, owner=file_component.subject_file_owner, grantee=auth_component.identity,
                                       check_for=FilePermissions.READ.value, check_until=datetime.fromtimestamp(header_component.sender_timestamp)):
        err_str: str = f'User {auth_component.identity} does not have read permission on file {file_component.subject_file} owned by {file_component.subject_file_owner}'
        asyncio.create_task(
            enqueue_log(waiting_period=SERVER_CONFIG.log_waiting_period, queue=log_queue,
                        log=ActivityLog(logged_by=LogAuthor.FILE_HANDLER.value,
                                        log_category=LogType.PERMISSION.value,log_details=err_str,
                                        severity=Severity.TRACE.value,
                                        user_concerned=auth_component.identity)))
        
        raise InsufficientPermissions(err_str)
    
    fpath: os.PathLike = os.path.join(file_component.subject_file_owner, file_component.subject_file)
    read_data, cursor_position, eof_reached = await read_file(root=SERVER_CONFIG.root_directory, fpath=fpath,
                                                              deleted_cache=delete_cache, read_cache=read_cache,
                                                              cursor_position=file_component.cursor_position, nbytes=file_component.chunk_size, reader_keepalive=file_component.cursor_keepalive,
                                                              purge_reader=header_component.finish, identifier=auth_component.identity, cached=True)
    
    ongoing_amendment: bool = bool(file_locks.get(fpath))

    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_READ, ended_connection=header_component.finish, config=SERVER_CONFIG),
            ResponseBody(contents=orjson.dumps({'read' : read_data, 'ongoing_amendment' : ongoing_amendment}), return_partial=not eof_reached, chunk_number=file_component.chunk_number+1, cursor_position=cursor_position, keepalive_accepted=bool(get_reader(read_cache, fpath, auth_component.identity)))) 

async def handle_creation(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, file_component: BaseFileComponent) -> tuple[ResponseHeader, None]:
    if file_component.subject_file_owner != auth_component.identity:
        asyncio.create_task(
            enqueue_log(waiting_period=SERVER_CONFIG.log_waiting_period, queue=log_queue,
                        log=ActivityLog(logged_by=LogAuthor.FILE_HANDLER.value,
                                        log_category=LogType.PERMISSION.value,
                                        log_details=f'User {auth_component.identity} attempted to create files in /{file_component.subject_file_owner}',
                                        severity=Severity.TRACE.value)))
        
        raise InvalidFileData(f'As user {auth_component.identity}, you only have permission to create new files in your own directory and not /{file_component.subject_file_owner}')
    
    fpath, epoch = await create_file(root=SERVER_CONFIG.root_directory, owner=auth_component.identity, filename=file_component.subject_file)
    proxy: ConnectionProxy = await connection_master.request_connection(level=1)

    if fpath:
        # Add record for this file
        try:
            await proxy.execute('''INSERT INTO files (filename, owner, created_at)
                                VALUES (%s, %s, %s);''',
                                (file_component.subject_file, auth_component.identity, datetime.fromtimestamp(epoch), ))
            await proxy.execute('''INSERT INTO file_permissions (file_owner, filename, grantee, role, granted_by, granted_at)
                                VALUES (%s, %s, %s, %s, %s, %s);''',
                                (auth_component.identity, file_component.subject_file, auth_component.identity,
                                RoleTypes.OWNER.value, auth_component.identity, datetime.fromtimestamp(header_component.sender_timestamp),))
        finally:
            await connection_master.reclaim_connection(proxy)
    else:
        asyncio.create_task(enqueue_log(waiting_period=SERVER_CONFIG.log_waiting_period, queue=log_queue,
                                        log=ActivityLog(logged_by=LogAuthor.FILE_HANDLER.value,
                                                        log_category=LogType.INTERNAL.value,
                                                        log_details=f'Failed to create file {fpath}',
                                                        severity=Severity.TRACE.value,
                                                        user_concerned=auth_component.identity)))
        
        raise FileConflict(file_component.subject_file, username=auth_component.identity)
    
    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_FILE_CREATION.value, ended_connection=header_component.finish, config=SERVER_CONFIG),
            ResponseBody(return_partial=False, keepalive_accepted=False, contents={'path' : fpath, 'iso_epoch' : datetime.fromtimestamp(epoch).isoformat()}))
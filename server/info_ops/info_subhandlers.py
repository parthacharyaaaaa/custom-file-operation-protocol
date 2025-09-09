'''Subhandler routines for INFO operations'''
# TODO: Perhaps add a caching mechanism for DB reads?
import asyncio
from typing import Any, Final, Union

from models.flags import InfoFlags
from models.response_codes import SuccessFlags
from models.response_models import ResponseHeader, ResponseBody
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BaseInfoComponent

import orjson

from psycopg.rows import dict_row
from psycopg import sql

from server import errors
from server.config.server_config import ServerConfig
from server.database.connections import ConnectionPoolManager
from server.database import models as db_models, utils as db_utils
from server.info_ops.utils import derive_file_identity, get_local_filedata, get_local_storage_data

file_permissions_selection_query: Final[sql.SQL] = sql.SQL('''SELECT {projection} FROM file_permissions
                                                           WHERE file_owner = %s AND filename = %s;''')

file_data_selection_query: Final[sql.SQL] = sql.SQL('''SELECT {projection}
                                                    FROM files
                                                    WHERE owner = %s AND filename = %s;''')

__all__ = ('handle_heartbeat',
           'handle_permission_query',
           'handle_filedata_query',
           'handle_user_query',
           'handle_storage_query',
           'handle_ssl_query')

async def handle_heartbeat(header_component: BaseHeaderComponent, server_config: ServerConfig) -> tuple[ResponseHeader, None]:
    '''Send a heartbeat signal back to the client'''
    return (
        ResponseHeader.from_server(config=server_config, code=SuccessFlags.HEARTBEAT.value, version=header_component.version, ended_connection=header_component.finish),
        None
    )

async def handle_permission_query(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, info_component: BaseInfoComponent,
                                    connection_master: ConnectionPoolManager, server_config: ServerConfig) -> tuple[ResponseHeader, ResponseBody]:
    owner, filename = derive_file_identity(info_component.subject_resource)
    async with await connection_master.request_connection(1) as proxy:
        if not await db_utils.check_file_permission(filename=filename, owner=owner, grantee=auth_component.identity,
                                                    check_for=db_models.FilePermissions.MANAGE_RW.value,
                                                    connection_master=connection_master, proxy=proxy):
            raise errors.InsufficientPermissions
        
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(file_permissions_selection_query.format(projection=sql.SQL("*" if (header_component.subcategory & InfoFlags.VERBOSE) else "grantee, role")),
                                 (owner, filename))
            result_set: list[dict[str, Any]] = await cursor.fetchall()

            return (ResponseHeader.from_server(server_config, SuccessFlags.SUCCESSFUL_QUERY_ANSWER.value, ended_connection=header_component.finish),
                    ResponseBody(contents={result.pop('grantee') : result for result in result_set}))

async def handle_filedata_query(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, info_component: BaseInfoComponent,
                                connection_master: ConnectionPoolManager, server_config: ServerConfig) -> tuple[ResponseHeader, ResponseBody]:
    owner, filename = derive_file_identity(info_component.subject_resource)
    async with await connection_master.request_connection(1) as proxy:
        if not await db_utils.check_file_permission(filename=filename, owner=owner, grantee=auth_component.identity,
                                                     check_for=db_models.FilePermissions.MANAGE_RW.value,
                                                     connection_master=connection_master, proxy=proxy):
            raise errors.InsufficientPermissions
        
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(file_data_selection_query.format(projection=sql.SQL('*')),
                                 (owner, filename))
            file_data: dict[str, Any] = await cursor.fetchone()

            if header_component.subcategory & InfoFlags.VERBOSE:
                file_data |= get_local_filedata(server_config.files_directory.joinpath(owner, filename))

            return (ResponseHeader.from_server(server_config, SuccessFlags.SUCCESSFUL_QUERY_ANSWER.value, ended_connection=header_component.finish),
                    ResponseBody(contents=file_data))

async def handle_user_query(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent,
                            connection_master: ConnectionPoolManager, server_config: ServerConfig) -> tuple[ResponseHeader, ResponseBody]:
    async with await connection_master.request_connection(1) as proxy:
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute('''SELECT username, created_at
                                    FROM users
                                    WHERE username = %s;''',
                                    (auth_component.identity,))
            user_data: dict[str, Any] = await cursor.fetchone()
            if header_component.subcategory & InfoFlags.VERBOSE:
                await cursor.execute('''SELECT file_owner, filename, role, granted_at, granted_by, granted_until
                                        FROM file_permissions
                                        WHERE grantee = %s;''',
                                        (auth_component.identity,))
                user_data |= {'files' : {f"{res.pop('file_owner')}/{res.pop('filename')}" : res
                                                    for res in
                                                    await cursor.fetchall()}}
                

            return (ResponseHeader.from_server(server_config, SuccessFlags.SUCCESSFUL_QUERY_ANSWER.value, ended_connection=header_component.finish),
                    ResponseBody(contents=user_data))

async def handle_storage_query(header_component: BaseHeaderComponent,
                               auth_component: BaseAuthComponent,
                               info_component: BaseInfoComponent,
                               server_config: ServerConfig) -> tuple[ResponseHeader, ResponseBody]:
    scan_task: asyncio.Task = asyncio.create_task(asyncio.to_thread(get_local_storage_data, root=server_config.files_directory, user=auth_component.identity))
    storage_data: dict[str, Any] = await asyncio.wait_for(scan_task, 10)
    storage_data.update({'storage_left' : server_config.user_max_storage - storage_data['storage_used'],
                         'files_left' : server_config.user_max_files - storage_data['files_made']})
    return (ResponseHeader.from_server(server_config, SuccessFlags.SUCCESSFUL_QUERY_ANSWER.value, ended_connection=header_component.finish),
            ResponseBody(contents=storage_data))

async def handle_ssl_query(server_config: ServerConfig) -> tuple[ResponseHeader, ResponseBody]:
    rollover_data: dict[str, dict[str, Union[str, float]]] = {}
    if server_config.rollover_data_filepath.exists() and (data:=server_config.rollover_data_filepath.read_bytes()):
        rollover_data = orjson.loads(data)
    
    return (ResponseHeader.from_server(server_config, SuccessFlags.SUCCESSFUL_QUERY_ANSWER.value),
            ResponseBody(contents={'rollover_data' : rollover_data}))
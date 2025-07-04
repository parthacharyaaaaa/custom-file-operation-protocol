import orjson
import psycopg.errors as pg_exc
from psycopg.rows import Row, dict_row
from response_codes import SuccessFlags
from server.bootup import connection_master
from server.database.models import role_types
from server.errors import OperationContested, DatabaseFailure, FileNotFound, FileConflict
from server.models.request_model import BaseHeaderComponent, BaseAuthComponent, BasePermissionComponent
from server.models.response_models import ResponseHeader, ResponseBody
from server.connectionpool import ConnectionProxy
from typing import Any, Optional, Literal

# TODO: Add logging for database-related failures

async def check_file_permission(filename: str, owner: str, grantee: str, check_for: role_types, proxy: Optional[ConnectionProxy] = None, level: Optional[Literal[1,2,3]] = 1) -> bool:
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
            return role_mapping['role'] == check_for
    finally:
        await connection_master.reclaim_connection(proxy)


async def publicise_file(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, permission_component: BasePermissionComponent) -> tuple[ResponseHeader, None]:
    proxy: ConnectionProxy = connection_master.request_connection(level=1)
    try:
        async with proxy.cursor(row_factory=dict_row) as cursor:
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


async def hide_file(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, permission_component: BasePermissionComponent) -> tuple[ResponseHeader, None]:
    proxy: ConnectionProxy = connection_master.request_connection(level=1)
    try:
        async with proxy.cursor(row_factory = dict_row) as cursor:
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


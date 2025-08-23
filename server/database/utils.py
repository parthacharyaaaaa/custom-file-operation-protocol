from typing import Any, Optional, Literal
from datetime import datetime

from models.permissions import FilePermissions

from psycopg.rows import dict_row
from psycopg import sql

from server.database.connections import ConnectionPoolManager, ConnectionProxy

__all__ = ('check_file_permission', 'get_user')

async def check_file_permission(filename: str, owner: str, grantee: str,
                                check_for: FilePermissions,
                                connection_master: ConnectionPoolManager, proxy: Optional[ConnectionProxy] = None, level: Optional[Literal[1,2,3]] = 1,
                                check_until: Optional[datetime] = None) -> bool:
    reclaim_after: bool = proxy is None
    if not proxy:
        proxy: ConnectionProxy = await connection_master.request_connection(level=level)
    try:
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute('''SELECT roles.permission
                                 FROM roles
                                 INNER JOIN file_permissions fp
                                 ON roles.role = fp.role
                                 WHERE fp.file_owner = %s AND fp.filename = %s AND fp.grantee = %s AND (fp.granted_until > %s OR fp.granted_until IS NULL)
                                 AND roles.permission = %s;''',
                                 (owner, filename, grantee, check_until or datetime.now(), check_for,))
            role_mapping: dict[str, str] = await cursor.fetchone()
    finally:
        if reclaim_after:
            await connection_master.reclaim_connection(proxy)
    
    return bool(role_mapping)

async def get_user(username: str,
                   connection_master: ConnectionPoolManager, proxy: Optional[ConnectionProxy] = None,
                   reclaim_after: bool = False,
                   lock_record: bool = False,
                   level: Literal[1,2,3] = 1,
                   check_existence: bool = False) -> Optional[dict[str, Any]]:
    if not proxy:
        reclaim_after = True
        proxy: ConnectionProxy = await connection_master.request_connection(level)
    query: sql.SQL = (sql.SQL('''SELECT {projection}
                             FROM users
                             WHERE username = {username}
                             {lock};''')
                             .format(projection=sql.SQL("username" if check_existence else "*"),
                                     username=sql.Literal(username),
                                     lock=sql.SQL('FOR UPDATE' if lock_record else '')))
    try:
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(query)
            return await cursor.fetchone()
    finally:
        if reclaim_after:
            await connection_master.reclaim_connection(proxy)
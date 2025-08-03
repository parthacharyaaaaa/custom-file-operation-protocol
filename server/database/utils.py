from typing import Optional, Literal
from datetime import datetime

from models.permissions import FilePermissions

from psycopg.rows import dict_row

from server.connectionpool import ConnectionPoolManager, ConnectionProxy

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
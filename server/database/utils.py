'''Database utilities'''

from typing import Any, Optional, Literal
from datetime import datetime

from models.permissions import FilePermissions

from psycopg.rows import dict_row
from psycopg import sql

from server.database.connections import ConnectionPoolManager, ConnectionPriority, ConnectionProxy

__all__ = ('check_file_permission', 'get_user')

async def check_file_permission(filename: str, owner: str, grantee: str,
                                check_for: FilePermissions,
                                connection_master: ConnectionPoolManager,
                                proxy: Optional[ConnectionProxy] = None,
                                level: ConnectionPriority = ConnectionPriority.LOW,
                                check_until: Optional[datetime] = None) -> bool:
    '''Check whether a grantee has a specific permission on a file.

    Args:
        filename (str): Name of the file to check permissions for.
        owner (str): Owner of the file.
        grantee (str): User whose permission is being checked.
        check_for (FilePermissions): Specific permission to check (e.g., read, write, execute).
        connection_master (ConnectionPoolManager): Manager to obtain database connections.
        proxy (Optional[ConnectionProxy]): Optional existing database connection to use. If None, a connection will be requested.
        level (Optional[Literal[1,2,3]]): Permission level for the connection, defaults to 1.
        check_until (Optional[datetime]): Optional cutoff datetime; permissions granted beyond this time are ignored.

    Returns:
        bool: True if the grantee has the specified permission on the file, False otherwise.
    '''

    reclaim_after: bool = proxy is None
    if not proxy:
        proxy = await connection_master.request_connection(level=level)
    try:
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute('''SELECT roles.permission
                                 FROM roles
                                 INNER JOIN file_permissions fp
                                 ON roles.role = fp.role
                                 WHERE fp.file_owner = %s AND fp.filename = %s AND fp.grantee = %s AND (fp.granted_until > %s OR fp.granted_until IS NULL)
                                 AND roles.permission = %s;''',
                                 (owner, filename, grantee, check_until or datetime.now(), check_for.value,))
            role_mapping: Optional[dict[str, str]] = await cursor.fetchone()
    finally:
        if reclaim_after:
            await connection_master.reclaim_connection(proxy)
    
    return bool(role_mapping)

async def get_user(username: str,
                   connection_master: ConnectionPoolManager, proxy: Optional[ConnectionProxy] = None,
                   reclaim_after: bool = False,
                   lock_record: bool = False,
                   level: ConnectionPriority = ConnectionPriority.LOW,
                   check_existence: bool = False) -> Optional[dict[str, Any]]:
    '''Retrieve user information from the database.

    Args:
        username (str): Username of the user to retrieve.
        connection_master (ConnectionPoolManager): Manager to obtain database connections.
        proxy (Optional[ConnectionProxy]): Optional existing database connection to use. If None, a connection will be requested.
        reclaim_after (bool): Whether to return the connection to the pool after use, defaults to False.
        lock_record (bool): Whether to lock the user record for update, defaults to False.
        level (Literal[1,2,3]): Permission level for the connection, defaults to 1.
        check_existence (bool): If True, only checks if the user exists and returns minimal data, defaults to False.

    Returns:
        Optional[dict[str,Any]]: Dictionary containing user data if found, or None if the user does not exist.
    '''

    if not proxy:
        reclaim_after = True
        proxy = await connection_master.request_connection(level)
    query: sql.Composed = (sql.SQL('''SELECT {projection}
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

async def check_file_existence(filename: str,
                               owner: str,
                               connection_master: ConnectionPoolManager,
                               proxy: Optional[ConnectionProxy] = None,
                               reclaim_after: bool = False,
                               level: ConnectionPriority = ConnectionPriority.LOW) -> bool:
    '''Check whether a file exists in the database.

    Args:
        filename (str): Name of the file to check.
        connection_master (ConnectionPoolManager): Manager to obtain database connections.
        proxy (Optional[ConnectionProxy]): Optional existing database connection to use. If None, a connection will be requested.
        reclaim_after (bool): Whether to return the connection to the pool after use, defaults to False.
        level (Literal[1,2,3]): Permission level for the connection, defaults to 1.

    Returns:
        bool: Whether file exists.
    '''

    if not proxy:
        if not connection_master:
            raise ValueError('Missing connection master for requesting proxy')
        
        reclaim_after = True
        proxy = await connection_master.request_connection(level)
    try:
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute('''SELECT filename
                                 FROM files
                                 WHERE owner = %s AND filename = %s''',
                                 (owner, filename))
            return bool(await cursor.fetchone())
    finally:
        if reclaim_after:
            await connection_master.reclaim_connection(proxy)
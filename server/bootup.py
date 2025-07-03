'''Helper module for loading all required instances whenever the server starts'''
import asyncio
from server.authz.user_master import UserManager
from server.connectionpool import ConnectionPoolManager
from server.config import ServerConfig

connection_master: ConnectionPoolManager = None
user_master: UserManager = None
file_locks: dict[str, asyncio.Lock] = None

def init_connection_master(conninfo: str, config: type[ServerConfig]) -> ConnectionPoolManager:
    global connection_master
    connection_master = ConnectionPoolManager(conninfo, config.CONNECTION_LEASE_DURATION.value, *config.MAX_CONNECTIONS.value, connection_timeout=config.CONNECTION_TIMEOUT.value, connection_refresh_timer=config.CONNECTION_REFRESH_TIMER.value)

    return connection_master

def init_user_master(config: type[ServerConfig]) -> UserManager:
    global user_master
    user_master = UserManager()

    return user_master

def init_file_lock() -> set:
    global file_locks
    file_locks = {}

    return file_locks
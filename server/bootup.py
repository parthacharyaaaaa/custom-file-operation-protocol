'''Helper module for loading all required instances whenever the server starts'''
import asyncio
from server.authz.session_master import SessionMaster
from server.connectionpool import ConnectionPoolManager
from server.config import ServerConfig

connection_master: ConnectionPoolManager = None
session_master: SessionMaster = None
file_locks: dict[str, asyncio.Lock] = None

def init_connection_master(conninfo: str, config: type[ServerConfig]) -> ConnectionPoolManager:
    global connection_master
    connection_master = ConnectionPoolManager(conninfo, config.CONNECTION_LEASE_DURATION.value, *config.MAX_CONNECTIONS.value, connection_timeout=config.CONNECTION_TIMEOUT.value, connection_refresh_timer=config.CONNECTION_REFRESH_TIMER.value)

    return connection_master

def init_session_master(config: type[ServerConfig]) -> SessionMaster:
    global session_master
    session_master = SessionMaster()

    return session_master

def init_file_lock() -> set:
    global file_locks
    file_locks = {}

    return file_locks
'''Helper module for loading all required instances whenever the server starts'''
import asyncio
from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncBufferedIOBase
from cachetools import TTLCache
from server.authz.user_manager import UserManager
from server.connectionpool import ConnectionPoolManager
from server.config import ServerConfig

# Singleton objects
connection_master: ConnectionPoolManager = None
user_master: UserManager = None

# Global locks
file_locks: dict[str, asyncio.Lock] = None

# Caches
delete_cache: TTLCache[str, True] = None
read_cache: TTLCache[str, dict[str, AsyncBufferedReader]] = None
write_cache: TTLCache[str, dict[str, AsyncBufferedIOBase]] = None
append_cache: TTLCache[str, dict[str, AsyncBufferedIOBase]] = None

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

def init_caches() -> set:
    global read_cache, write_cache, append_cache, delete_cache
    read_cache = TTLCache(maxsize=ServerConfig.FILE_CACHE_SIZE.value, ttl=ServerConfig.FILE_CACHE_TTL.value)
    write_cache = TTLCache(maxsize=ServerConfig.FILE_CACHE_SIZE.value, ttl=ServerConfig.FILE_CACHE_TTL.value)
    append_cache = TTLCache(maxsize=ServerConfig.FILE_CACHE_SIZE.value, ttl=ServerConfig.FILE_CACHE_TTL.value)
    delete_cache= TTLCache(maxsize=ServerConfig.FILE_CACHE_SIZE.value, ttl=ServerConfig.FILE_CACHE_TTL.value)
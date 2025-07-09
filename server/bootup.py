'''Helper module for loading all required instances whenever the server starts'''
import asyncio
from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncBufferedIOBase
from cachetools import TTLCache
from math import inf
from server.authz.user_manager import UserManager
from server.config.server_config import ServerConfig
from server.connectionpool import ConnectionPoolManager
from server.logging import flush_logs

# Singleton objects
connection_master: ConnectionPoolManager = None
user_master: UserManager = None

# Global locks
file_locks: TTLCache[str, bytes] = None

# Logging
log_queue: asyncio.PriorityQueue = None

# Caches
delete_cache: TTLCache[str, True] = None
read_cache: TTLCache[str, dict[str, AsyncBufferedReader]] = None
write_cache: TTLCache[str, dict[str, AsyncBufferedIOBase]] = None
append_cache: TTLCache[str, dict[str, AsyncBufferedIOBase]] = None

async def init_connection_master(conninfo: str, config: ServerConfig) -> ConnectionPoolManager:
    global connection_master
    connection_master = ConnectionPoolManager(config.connection_lease_duration, *config.max_connections,
                                              connection_timeout=config.connection_timeout,
                                              connection_refresh_timer=config.connection_refresh_interval)
    
    await connection_master.populate_pools(conninfo)
    return connection_master

def init_user_master(config: ServerConfig) -> UserManager:
    global user_master
    user_master = UserManager(connection_master=connection_master, log_queue=log_queue, session_lifespan=config.session_lifespan)

    return user_master

def init_file_lock(config: ServerConfig) -> set:
    global file_locks
    file_locks = TTLCache(maxsize=inf, ttl=config.file_lock_ttl)

    return file_locks

def init_caches(config: ServerConfig) -> None:
    global read_cache, write_cache, append_cache, delete_cache
    read_cache = TTLCache(maxsize=config.file_cache_size, ttl=config.file_cache_ttl)
    write_cache = TTLCache(maxsize=config.file_cache_size, ttl=config.file_cache_ttl)
    append_cache = TTLCache(maxsize=config.file_cache_size, ttl=config.file_cache_ttl)
    delete_cache= TTLCache(maxsize=config.file_cache_size, ttl=config.file_cache_ttl)

def init_logger(config: ServerConfig) -> None:
    global log_queue
    log_queue = asyncio.PriorityQueue(inf)

    asyncio.create_task(flush_logs(connection_master=connection_master, queue=log_queue, batch_size=config.log_batch_size, waiting_period=config.log_waiting_period, flush_interval=config.log_interval))
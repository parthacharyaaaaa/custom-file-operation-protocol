'''Helper module for loading all required instances whenever the server starts'''
import asyncio
from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncBufferedIOBase
from cachetools import TTLCache
from math import inf
from server.authz.user_manager import UserManager
from server.config.server_config import SERVER_CONFIG
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
amendment_cache: TTLCache[str, dict[str, AsyncBufferedIOBase]] = None

async def init_connection_master(conninfo: str, ) -> ConnectionPoolManager:
    global connection_master
    connection_master = ConnectionPoolManager(SERVER_CONFIG.connection_lease_duration, *SERVER_CONFIG.max_connections,
                                              connection_timeout=SERVER_CONFIG.connection_timeout,
                                              connection_refresh_timer=SERVER_CONFIG.connection_refresh_interval)
    
    await connection_master.populate_pools(conninfo)
    return connection_master

def init_user_master() -> UserManager:
    global user_master
    user_master = UserManager(connection_master=connection_master, log_queue=log_queue, session_lifespan=SERVER_CONFIG.session_lifespan)

    return user_master

def init_file_lock() -> set:
    global file_locks
    file_locks = TTLCache(maxsize=inf, ttl=SERVER_CONFIG.file_lock_ttl)

    return file_locks

def init_caches() -> None:
    global read_cache, amendment_cache, delete_cache
    read_cache = TTLCache(maxsize=SERVER_CONFIG.file_cache_size, ttl=SERVER_CONFIG.file_cache_ttl)
    amendment_cache = TTLCache(maxsize=SERVER_CONFIG.file_cache_size, ttl=SERVER_CONFIG.file_cache_ttl)
    delete_cache = TTLCache(maxsize=SERVER_CONFIG.file_cache_size, ttl=SERVER_CONFIG.file_cache_ttl)

def init_logger() -> None:
    global log_queue
    log_queue = asyncio.PriorityQueue(inf)

    asyncio.create_task(flush_logs(connection_master=connection_master, queue=log_queue, batch_size=SERVER_CONFIG.log_batch_size, waiting_period=SERVER_CONFIG.log_waiting_period, flush_interval=SERVER_CONFIG.log_interval))
'''Helper module for loading all required instances whenever the server starts'''
import asyncio
from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncBufferedIOBase
from cachetools import TTLCache
from math import inf
from server.config.server_config import ServerConfig
from server.authz.user_manager import UserManager
from server.connectionpool import ConnectionPoolManager
from server.logging import flush_logs
import server.database.models as db_models

async def create_connection_master(conninfo: str, config: ServerConfig) -> ConnectionPoolManager:
    connection_master = ConnectionPoolManager(config.connection_lease_duration, *config.max_connections,
                                              connection_timeout=config.connection_timeout,
                                              connection_refresh_timer=config.connection_refresh_interval)
    
    await connection_master.populate_pools(conninfo)
    return connection_master

def create_user_master(connection_master: ConnectionPoolManager, config: ServerConfig, log_queue: asyncio.PriorityQueue[tuple[db_models.ActivityLog, int]]) -> UserManager:
    return UserManager(connection_master=connection_master,
                       log_queue=log_queue,
                       session_lifespan=config.session_lifespan)

def create_file_lock(config: ServerConfig) -> TTLCache[str, bytes]:
    return TTLCache(maxsize=inf, ttl=config.file_lock_ttl)

def create_amendment_cache(config: ServerConfig) -> tuple[TTLCache[str, dict[str, AsyncBufferedReader]],
                                                          TTLCache[str, dict[str, AsyncBufferedIOBase]],
                                                          TTLCache[str, str]]:
    
    read_cache = TTLCache(maxsize=config.file_cache_size, ttl=config.file_cache_ttl)
    amendment_cache = TTLCache(maxsize=config.file_cache_size, ttl=config.file_cache_ttl)
    delete_cache = TTLCache(maxsize=config.file_cache_size, ttl=config.file_cache_ttl)

    return read_cache, amendment_cache, delete_cache

def create_log_queue() -> asyncio.PriorityQueue[tuple[db_models.ActivityLog, int]]:
    return asyncio.PriorityQueue(inf)

def start_logger(log_queue: asyncio.PriorityQueue[tuple[db_models.ActivityLog, int]], config: ServerConfig, connection_master: ConnectionPoolManager) -> None:
    asyncio.create_task(flush_logs(connection_master=connection_master,
                                   queue=log_queue,
                                   batch_size=config.log_batch_size,
                                   waiting_period=config.log_waiting_period,
                                   flush_interval=config.log_interval))
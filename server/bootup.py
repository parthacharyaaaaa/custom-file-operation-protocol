'''Helper module for loading all required instances whenever the server starts'''
import os
import asyncio
from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncBufferedIOBase
from math import inf
from typing import Any, Optional

from cachetools import TTLCache

from server import logging
from server.authz.user_manager import UserManager
from server.config.server_config import ServerConfig
from server.connectionpool import ConnectionPoolManager
import server.database.models as db_models

import pytomlpp

__all__ = ('create_server_config', 'create_log_queue', 'create_connection_master', 'create_caches', 'create_file_lock', 'create_user_master', 'start_logger')

def create_server_config(dirname: Optional[str] = None) -> ServerConfig:
    loaded_constants: dict[str, Any] = pytomlpp.load(dirname or os.path.join(os.path.dirname(__file__), 'config', 'server_config.toml'))

    # Laziest code I have ever written
    SERVER_CONFIG = ServerConfig.model_validate({'version' :loaded_constants['version']} | loaded_constants['network'] | loaded_constants['database'] | loaded_constants['file'] | loaded_constants['auth'] | loaded_constants['logging'])
    SERVER_CONFIG.root_directory = os.path.join(os.path.dirname(__file__), SERVER_CONFIG.root_directory)
    
    return SERVER_CONFIG

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

def create_caches(config: ServerConfig) -> tuple[TTLCache[str, dict[str, AsyncBufferedReader]],
                                                          TTLCache[str, dict[str, AsyncBufferedIOBase]],
                                                          TTLCache[str, str]]:
    
    read_cache = TTLCache(maxsize=config.file_cache_size, ttl=config.file_cache_ttl)
    amendment_cache = TTLCache(maxsize=config.file_cache_size, ttl=config.file_cache_ttl)
    delete_cache = TTLCache(maxsize=config.file_cache_size, ttl=config.file_cache_ttl)

    return read_cache, amendment_cache, delete_cache

def create_log_queue(config: ServerConfig) -> asyncio.Queue[db_models.ActivityLog]:
    return asyncio.Queue(config.log_queue_size)

def start_logger(log_queue: asyncio.Queue[db_models.ActivityLog], config: ServerConfig, connection_master: ConnectionPoolManager) -> None:
    asyncio.create_task(logging.flush_logs(connection_master=connection_master,
                                           queue=log_queue,
                                           batch_size=config.log_batch_size,
                                           waiting_period=config.log_waiting_period,
                                           flush_interval=config.log_interval))

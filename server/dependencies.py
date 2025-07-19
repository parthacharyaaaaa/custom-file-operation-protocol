from types import MappingProxyType
from typing import Any

from asyncio import PriorityQueue
from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncBufferedIOBase
from cachetools import TTLCache

from server.authz.user_manager import UserManager
from server.config.server_config import ServerConfig
from server.connectionpool import ConnectionPoolManager

__all__ = ('populate_dependency_registry',)

def populate_dependency_registry(server: ServerConfig,
                         user_manager: UserManager,
                         connection_pool_manager: ConnectionPoolManager,
                         log_queue: PriorityQueue,
                         reader_cache: TTLCache[str, dict[str, AsyncBufferedReader]],
                         amendment_cache: TTLCache[str, dict[str, AsyncBufferedIOBase]],
                         file_locks: TTLCache[str, bytes]) -> MappingProxyType[type, Any]:
    
    return MappingProxyType({
        ServerConfig : server,
        UserManager : user_manager,
        ConnectionPoolManager : connection_pool_manager,
        PriorityQueue : log_queue,
        TTLCache[str, dict[str, AsyncBufferedReader]] : reader_cache,
        TTLCache[str, dict[str, AsyncBufferedIOBase]] : amendment_cache,
        TTLCache[str, bytes] : file_locks
})
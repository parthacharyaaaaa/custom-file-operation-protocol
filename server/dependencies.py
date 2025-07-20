from functools import lru_cache, partial
import inspect
from types import MappingProxyType
from typing import Any, NewType, Callable, Optional, Annotated

import asyncio
from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncBufferedIOBase
from cachetools import TTLCache

from models.response_models import ResponseHeader, ResponseBody
from models.singletons import SingletonMetaclass

from server.authz.user_manager import UserManager
from server.config.server_config import ServerConfig
from server.connectionpool import ConnectionPoolManager
from server.database import models as db_models

import pydantic

__all__ = ('NT_GLOBAL_LOG_QUEUE', 'NT_GLOBAL_READ_CACHE', 'NT_GLOBAL_AMEND_CACHE', 'NT_GLOBAL_DELETE_CACHE', 'NT_GLOBAL_FILE_LOCK',
           'ServerSingletonsRegistry',)

# NewType annotations for global singletons with data types that can be repeated in a function signature
NT_GLOBAL_LOG_QUEUE = NewType('NT_GLOBAL_LOG_QUEUE', asyncio.queues.PriorityQueue[tuple[db_models.ActivityLog, int]])
NT_GLOBAL_READ_CACHE = NewType('NT_GLOBAL_READ_CACHE', TTLCache[str, dict[str, AsyncBufferedReader]])
NT_GLOBAL_AMEND_CACHE = NewType('NT_GLOBAL_AMEND_CACHE', TTLCache[str, dict[str, AsyncBufferedIOBase]])
NT_GLOBAL_DELETE_CACHE = NewType('NT_GLOBAL_DELETE_CACHE', TTLCache[str, str])
NT_GLOBAL_FILE_LOCK = NewType('NT_GLOBAL_FILE_LOCK', TTLCache[str, bytes])

@pydantic.dataclasses.dataclass(slots=True, config={'arbitrary_types_allowed': True})
class ServerSingletonsRegistry(metaclass=SingletonMetaclass):
    server_config: ServerConfig
    user_manager: UserManager
    connection_pool_manager: ConnectionPoolManager
    log_queue: NT_GLOBAL_LOG_QUEUE
    reader_cache: NT_GLOBAL_READ_CACHE
    amendment_cache: NT_GLOBAL_AMEND_CACHE
    deletion_cache: NT_GLOBAL_DELETE_CACHE
    file_locks: NT_GLOBAL_FILE_LOCK

    _registry_reverse_mapping: Annotated[Optional[MappingProxyType[type, str]], pydantic.Field(default=None)]

    def __post_init__(self) -> None:
        self._registry_reverse_mapping = MappingProxyType({v.type : k for k, v in self.__dataclass_fields__.items()})

    @property
    def registry_reverse_mapping(self) -> MappingProxyType[type, str]:
        return self._registry_reverse_mapping

    def inject_global_singletons(self,
                                 func: Callable[..., tuple[ResponseHeader, Optional[ResponseBody]]],
                                 **overrides_kwargs) -> Callable[..., tuple[ResponseHeader, Optional[ResponseBody]]]:
        bound_args: dict[str, Any] = {}
        for paramname, paramtype in inspect.signature(func).parameters.items():
            if overridden_kwarg:=overrides_kwargs.get(paramname):
                bound_args[paramname] = overridden_kwarg
                continue
            
            singleton: str = self.registry_reverse_mapping.get(paramtype.annotation)
            if not singleton:
                raise TypeError(f'Parameter mismatch on calling {func} with parameter {paramname} of type {paramtype}')
            bound_args[paramname] = self.__getattribute__(singleton)
        
        return partial(func, **bound_args)
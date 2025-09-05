from functools import partial
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
from server.database.connections import ConnectionPoolManager
from server.database import models as db_models

import pydantic

__all__ = ('GlobalLogQueueType',
           'GlobalReadCacheType',
           'GlobalAmendCacheType',
           'GlobalDeleteCacheType',
           'GlobalFileLockType',
           'ServerSingletonsRegistry')

# Utility objects for this module
_RegistryMissPlaceholder = NewType('_RegistryMissPlaceholder', None)
_singleton_registry_config_dict: pydantic.ConfigDict = pydantic.ConfigDict(
    {
        'arbitrary_types_allowed':True
    })


# NewType annotations for global singletons with data types that can be repeated in a function signature
GlobalLogQueueType = NewType('GlobalLogQueueType', asyncio.queues.Queue[db_models.ActivityLog])
GlobalReadCacheType = NewType('GlobalReadCacheType', TTLCache[str, dict[str, AsyncBufferedReader]])
GlobalAmendCacheType = NewType('GlobalAmendCacheType', TTLCache[str, dict[str, AsyncBufferedIOBase]])
GlobalDeleteCacheType = NewType('GlobalDeleteCacheType', TTLCache[str, str])
GlobalFileLockType = NewType('GlobalFileLockType', TTLCache[str, bytes])

@pydantic.dataclasses.dataclass(slots=True, config=_singleton_registry_config_dict)
class ServerSingletonsRegistry(metaclass=SingletonMetaclass):
    # Custom singleton classes are not assigned an explicit NewType 
    # since it is impossible to have a function signature having duplicate type annotations for them
    server_config: Annotated[ServerConfig, pydantic.Field(frozen=True)]
    user_manager: Annotated[UserManager, pydantic.Field(frozen=True)]
    connection_pool_manager: Annotated[ConnectionPoolManager, pydantic.Field(frozen=True)]

    log_queue: Annotated[GlobalLogQueueType, pydantic.Field(frozen=True)]
    reader_cache: Annotated[GlobalReadCacheType, pydantic.Field(frozen=True)]
    amendment_cache: Annotated[GlobalAmendCacheType, pydantic.Field(frozen=True)]
    deletion_cache: GlobalDeleteCacheType
    file_locks: GlobalFileLockType

    _registry_reverse_mapping: MappingProxyType[type, str] = pydantic.PrivateAttr(default={})

    def __post_init__(self) -> None:
        self._registry_reverse_mapping = MappingProxyType({
            ServerConfig : self.server_config,
            UserManager : self.user_manager,
            ConnectionPoolManager : self.connection_pool_manager,
            GlobalLogQueueType : self.log_queue,
            GlobalReadCacheType : self.reader_cache,
            GlobalAmendCacheType : self.amendment_cache,
            GlobalDeleteCacheType : self.deletion_cache,
            GlobalFileLockType : self.file_locks
        })

    @property
    def registry_reverse_mapping(self) -> MappingProxyType[type, str]:
        return self._registry_reverse_mapping

    def inject_global_singletons(self,
                                 func: Callable[..., tuple[ResponseHeader, Optional[ResponseBody]]],
                                 strict: bool = False,
                                 **overrides_kwargs) -> Callable[..., tuple[ResponseHeader, Optional[ResponseBody]]]:
        bound_args: dict[str, Any] = {}
        for paramname, paramtype in inspect.signature(func).parameters.items():
            if paramname in overrides_kwargs:
                bound_args[paramname] = overrides_kwargs[paramname]
                continue
            
            singleton: Any = self.registry_reverse_mapping.get(paramtype.annotation, _RegistryMissPlaceholder)
            if singleton != _RegistryMissPlaceholder:
                bound_args[paramname] = singleton
            elif strict:
                raise TypeError(f'Parameter mismatch on calling {func} with parameter {paramname} of type {paramtype}')
        
        return partial(func, **bound_args)

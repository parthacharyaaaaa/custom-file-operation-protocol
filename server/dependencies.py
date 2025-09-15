import asyncio
import inspect
from functools import partial
from typing import Any, Coroutine, Callable, NewType, Optional, TypeAlias, Union

from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncBufferedIOBase

from cachetools import TTLCache

from models.singletons import SingletonMetaclass
from models.response_models import ResponseHeader, ResponseBody

from server.authz.user_manager import UserManager
from server.config.server_config import ServerConfig
from server.database import models as db_models
from server.database.connections import ConnectionPoolManager
from server.file_ops.storage import StorageCache

import pydantic

__all__ = ('GlobalLogQueueType',
           'GlobalReadCacheType',
           'GlobalAmendCacheType',
           'GlobalDeleteCacheType',
           'GlobalFileLockType',
           'SingletonTypes',
           'ServerSingletonsRegistry')

# Utility objects for this module
_RegistryMissPlaceholder = NewType('_RegistryMissPlaceholder', None)
_singleton_registry_config_dict: pydantic.ConfigDict = pydantic.ConfigDict(
    {
        'arbitrary_types_allowed':True
    })


# NewType annotations for global singletons with data types that can be repeated in a function signature
class GlobalLogQueueType(asyncio.Queue[db_models.ActivityLog]): pass
class GlobalReadCacheType(TTLCache[str, dict[str, AsyncBufferedReader]]): pass
class GlobalAmendCacheType(TTLCache[str, dict[str, AsyncBufferedIOBase]]): pass
class GlobalDeleteCacheType(TTLCache[str, str]): pass
class GlobalFileLockType(TTLCache[str, str]): pass

SubhandlerResponse: TypeAlias = Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]

SingletonTypes: TypeAlias = Union[
    type[ServerConfig],
    type[UserManager],
    type[ConnectionPoolManager],
    type[StorageCache],
    type[GlobalAmendCacheType],
    type[GlobalDeleteCacheType],
    type[GlobalReadCacheType],
    type[GlobalFileLockType],
    type[GlobalLogQueueType],
]

@pydantic.dataclasses.dataclass(slots=True, config=_singleton_registry_config_dict)
class ServerSingletonsRegistry(metaclass=SingletonMetaclass):
    # Custom singleton classes are not assigned an explicit NewType 
    # since it is impossible to have a function signature having duplicate type annotations for them
    deletion_cache: TTLCache[str, str]
    file_locks: TTLCache[str, bytes]
    server_config: ServerConfig = pydantic.Field(frozen=True)
    user_manager: UserManager = pydantic.Field(frozen=True)
    connection_pool_manager: ConnectionPoolManager = pydantic.Field(frozen=True)
    storage_cache: StorageCache = pydantic.Field(frozen=True)

    log_queue: asyncio.Queue[db_models.ActivityLog] = pydantic.Field(frozen=True)
    reader_cache: TTLCache[str, dict[str, AsyncBufferedReader]] = pydantic.Field(frozen=True)
    amendment_cache: TTLCache[str, dict[str, AsyncBufferedIOBase]] = pydantic.Field(frozen=True)

    _registry_reverse_mapping: dict[SingletonTypes, Any] = pydantic.PrivateAttr(default={})

    def __post_init__(self) -> None:
        self._registry_reverse_mapping = {
            ServerConfig : self.server_config,
            UserManager : self.user_manager,
            ConnectionPoolManager : self.connection_pool_manager,
            GlobalLogQueueType : self.log_queue,
            GlobalReadCacheType : self.reader_cache,
            GlobalAmendCacheType : self.amendment_cache,
            GlobalDeleteCacheType : self.deletion_cache,
            GlobalFileLockType : self.file_locks,
            StorageCache : self.storage_cache
        }

    @property
    def registry_reverse_mapping(self) -> dict[SingletonTypes, str]:
        return self._registry_reverse_mapping

    def inject_global_singletons(self,
                                 func: Callable[..., SubhandlerResponse],
                                 strict: bool = False,
                                 **overrides_kwargs) -> Callable[..., SubhandlerResponse]:
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

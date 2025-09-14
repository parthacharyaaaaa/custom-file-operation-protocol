'''Typing support for server-specific data structures'''

import asyncio
from typing import Any, Callable, Coroutine, Optional, TypeAlias, Union

from aiofiles.threadpool.binary import AsyncBufferedIOBase, AsyncBufferedReader

from server.dependencies import (GlobalFileLockType, GlobalLogQueueType,
                                 GlobalAmendCacheType, GlobalDeleteCacheType, GlobalReadCacheType,
                                 ServerConfig, ConnectionPoolManager, UserManager,
                                 ServerSingletonsRegistry)

from models.response_models import ResponseHeader, ResponseBody
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BaseInfoComponent, BaseFileComponent, BasePermissionComponent
from models.typing import SubcategoryFlag

__all__ = ('PermissionSubhandler',
           'InfoSubhandler',
           'AuthSubhandler',
           'FileSubhandler',
           'SubhandlerResponse',
           'ServerSingleton',
           'RequestSubhandler',
           'RequestHandler',
           'FileBuffer')

ServerSingleton: TypeAlias = Union[GlobalReadCacheType, GlobalAmendCacheType, GlobalDeleteCacheType,
                                   GlobalFileLockType, GlobalLogQueueType, ServerConfig,
                                   ConnectionPoolManager, UserManager]

PermissionSubhandler: TypeAlias = Callable[[BaseHeaderComponent, BaseAuthComponent, BasePermissionComponent],
                                      Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]]

InfoSubhandler: TypeAlias = Callable[[BaseHeaderComponent, BaseAuthComponent, BaseInfoComponent],
                                      Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]]

AuthSubhandler: TypeAlias = Callable[[BaseHeaderComponent, BaseAuthComponent],
                                      Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]]

FileSubhandler: TypeAlias = Callable[[BaseHeaderComponent, BaseAuthComponent, BaseFileComponent],
                                      Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]]

RequestSubhandler: TypeAlias = Union[AuthSubhandler, InfoSubhandler, FileSubhandler, PermissionSubhandler]

SubhandlerResponse: TypeAlias = Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]

RequestHandler: TypeAlias = Callable[[asyncio.StreamReader, BaseHeaderComponent, ServerSingletonsRegistry, dict[SubcategoryFlag, RequestSubhandler]], SubhandlerResponse]

FileBuffer: TypeAlias = Union[AsyncBufferedReader, AsyncBufferedIOBase]
'''Typing support for server-specific data structures'''

import asyncio
from enum import IntFlag
from typing import Any, Callable, Coroutine, Optional, TypeAlias, Union, Mapping, ParamSpec, Concatenate

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

P = ParamSpec('P')

ServerSingleton: TypeAlias = Union[GlobalReadCacheType, GlobalAmendCacheType, GlobalDeleteCacheType,
                                   GlobalFileLockType, GlobalLogQueueType, ServerConfig,
                                   ConnectionPoolManager, UserManager]

PermissionSubhandler: TypeAlias = Callable[
    Concatenate[BaseHeaderComponent, BaseAuthComponent, BasePermissionComponent, P],
    Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]
]

InfoSubhandler: TypeAlias = Callable[
    Concatenate[P],
    Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]
]

AuthSubhandler: TypeAlias = Callable[
    Concatenate[BaseHeaderComponent, BaseAuthComponent, P],
    Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]
]

FileSubhandler: TypeAlias = Callable[
    Concatenate[BaseHeaderComponent, BaseAuthComponent, BaseFileComponent, P],
    Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]]

RequestSubhandler: TypeAlias = Union[AuthSubhandler, InfoSubhandler, FileSubhandler, PermissionSubhandler]

SubhandlerResponse: TypeAlias = Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]

RequestHandler: TypeAlias = Callable[[asyncio.StreamReader,
                                      BaseHeaderComponent,
                                      ServerSingletonsRegistry,
                                      Mapping[Any, Any]
                                      ],
                                     SubhandlerResponse]

FileBuffer: TypeAlias = Union[AsyncBufferedReader, AsyncBufferedIOBase]
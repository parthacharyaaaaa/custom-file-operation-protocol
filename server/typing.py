'''Typing support for server-specific data structures'''

import asyncio
from typing import Any, Callable, Coroutine, Optional, TypeAlias, Union, Mapping, ParamSpec, Concatenate

from server.dependencies import ServerSingletonsRegistry

from models.response_models import ResponseHeader, ResponseBody
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BaseFileComponent, BasePermissionComponent

__all__ = ('PermissionSubhandler',
           'InfoSubhandler',
           'AuthSubhandler',
           'FileSubhandler',
           'SubhandlerResponse',
           'RequestSubhandler',
           'RequestHandler')

P = ParamSpec('P')

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

PartialRequestHandler: TypeAlias = Callable[Concatenate[asyncio.StreamReader, BaseHeaderComponent, ServerSingletonsRegistry, P],
                                             SubhandlerResponse]

'''Typing support for server-specific data structures'''

import asyncio
from typing import Any, Coroutine, Mapping, Optional, Protocol, TypeAlias, Union

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

SubhandlerResponse: TypeAlias = Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]
class AuthSubhandler(Protocol):
    def __call__(self,
                 header_component: BaseHeaderComponent,
                 auth_component: BaseAuthComponent,
                 *args : Any, **kwargs: Any) -> SubhandlerResponse: ...

class InfoSubhandler(Protocol):
    def __call__(self, *args, **kwargs: Any) -> SubhandlerResponse: ...

class FileSubhandler(Protocol):
    def __call__(self,
                 header_component: BaseHeaderComponent,
                 auth_component: BaseAuthComponent,
                 file_component: BaseFileComponent,
                 *args : Any, **kwargs: Any) -> SubhandlerResponse: ...
    
class PermissionSubhandler(Protocol):
    def __call__(self,
                 header_component: BaseHeaderComponent,
                 auth_component: BaseAuthComponent,
                 permission_component: BasePermissionComponent,
                 *args : Any, **kwargs: Any) -> SubhandlerResponse: ...

RequestSubhandler: TypeAlias = Union[AuthSubhandler, InfoSubhandler, FileSubhandler, PermissionSubhandler]

class RequestHandler(Protocol):
    def __call__(self,
                 stream_reader: asyncio.StreamReader,
                 header_component: BaseHeaderComponent,
                 server_singleton_registry: ServerSingletonsRegistry,
                 subhandler_mapping: Mapping[Any, Any]) -> SubhandlerResponse: ...
    
class PartialisedRequestHandler(Protocol):
    def __call__(self,
                 stream_reader: asyncio.StreamReader,
                 header_component: BaseHeaderComponent,
                 server_singleton_registry: ServerSingletonsRegistry,
                 subhandler_mapping: Mapping[Any, Any] = ...) -> SubhandlerResponse: ...
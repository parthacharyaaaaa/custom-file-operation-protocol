import asyncio

from models.flags import AuthFlags, CategoryFlag
from models.response_models import ResponseHeader, ResponseBody
from models.request_model import BaseHeaderComponent, BaseAuthComponent

from server.authz.auth_subhandlers import handle_registration, handle_login, handle_session_refresh, handle_password_change, handle_deletion, handle_session_termination
from server.comms_utils.incoming import process_component
from server.config.server_config import ServerConfig
from server.errors import InvalidAuthSemantic, UnsupportedOperation

from typing import Optional, Coroutine, Any, Callable, TypeAlias
from types import MappingProxyType

AUTH_SUBHABDLER: TypeAlias = Callable[[BaseHeaderComponent, BaseAuthComponent],
                                      Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]]

_AUTH_SUBHANDLER_MAPPING: MappingProxyType[int, AUTH_SUBHABDLER] = MappingProxyType(
    dict(
        zip(
            AuthFlags._member_map_.values(),
            [handle_registration, handle_login, handle_session_refresh, handle_password_change, handle_deletion, handle_session_termination]
        )
    )
)

async def top_auth_handler(reader: asyncio.StreamReader, header_component: BaseHeaderComponent, server_config: ServerConfig) -> tuple[ResponseHeader, Optional[ResponseBody]]:
    if not header_component.auth_size:
        raise InvalidAuthSemantic('Missing auth component in header, and no unauthenticated operation requested')

    auth_component: BaseAuthComponent = await process_component(n_bytes=header_component.auth_size, reader=reader, component_type='auth', timeout=server_config.read_timeout)

    if header_component.subcategory not in AuthFlags._value2member_map_:    # R level function name, absolutely vile.
        raise UnsupportedOperation(f'Unsupported operation for category: {CategoryFlag.AUTH._name_}')
    
    # Delegate actual handling to defined functions/coroutines
    subhandler = _AUTH_SUBHANDLER_MAPPING[header_component.subcategory]
    header, body = await subhandler(header_component, auth_component)

    return header, body
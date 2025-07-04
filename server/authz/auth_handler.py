import asyncio
from server.authz.auth_flags import AuthFlags
from server.authz.auth_operations import handle_registration, handle_login, handle_session_refresh, handle_password_change, handle_deletion, handle_session_termination
from server.config import CategoryFlag
from server.comms_utils.incoming import process_component
from server.errors import InvalidAuthSemantic, UnsupportedOperation
from server.models.request_model import BaseHeaderComponent, BaseAuthComponent
from server.models.response_models import ResponseHeader, ResponseBody
from typing import Optional, Coroutine, Any, Callable, TypeAlias
from types import MappingProxyType

AUTH_SUBHABDLER: TypeAlias = Callable[[BaseHeaderComponent, BaseAuthComponent],
                                      Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]]

_AUTH_SUBHANDLER_MAPPING: MappingProxyType[int, AUTH_SUBHABDLER] = MappingProxyType(
    dict(
        zip(
            AuthFlags._member_names_,
            [handle_registration, handle_login, handle_session_refresh, handle_password_change, handle_deletion, handle_session_termination]
        )
    )
)

async def top_auth_handler(reader: asyncio.StreamReader, header_component: BaseHeaderComponent) -> tuple[ResponseHeader, Optional[ResponseBody]]:
    if not header_component.auth_size:
        raise InvalidAuthSemantic('Missing auth component in header, and no unauthenticated operation requested')

    auth_component: BaseAuthComponent = await process_component(n_bytes=header_component.auth_size, reader=reader, component_type='auth')

    if header_component.subcategory not in AuthFlags._value2member_map_:    # R level function name, absolutely vile.
        raise UnsupportedOperation(f'Unsupported operation for category: {CategoryFlag.AUTH._name_}')
    
    # Delegate actual handling to defined functions/coroutines
    subhandler = _AUTH_SUBHANDLER_MAPPING[header_component.subcategory]
    header, body = await subhandler(header_component, auth_component)

    return header, body
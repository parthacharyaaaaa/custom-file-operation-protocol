import asyncio
from typing import Optional, TypeAlias, Callable, Coroutine, Any
from types import MappingProxyType

from models.flags import PermissionFlags, CategoryFlag
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BasePermissionComponent
from models.response_models import ResponseHeader, ResponseBody

from server.bootup import user_master
from server.comms_utils.incoming import process_component
from server.config.server_config import SERVER_CONFIG
from server.errors import InvalidHeaderSemantic, InvalidAuthSemantic, SlowStreamRate, UnsupportedOperation
from server.permission_ops.permission_operations import grant_permission, revoke_permission, hide_file, publicise_file, transfer_ownership

import orjson
from pydantic import ValidationError


PERMISSION_SUBHABDLER: TypeAlias = Callable[[BaseHeaderComponent, BaseAuthComponent, BasePermissionComponent],
                                      Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]]

_PERMISSION_SUBHANDLER_MAPPING: MappingProxyType[int, PERMISSION_SUBHABDLER] = MappingProxyType(
    dict(
        zip(
            PermissionFlags._member_names_[:-3],
            [grant_permission, revoke_permission, hide_file, publicise_file, transfer_ownership]
        )
    )
)


async def top_permission_handler(reader: asyncio.StreamReader, header_component: BaseHeaderComponent) -> tuple[ResponseHeader, Optional[ResponseBody]]:
    # Permission operations require authentication
    if not (header_component.auth_size and header_component.body_size):
        raise InvalidHeaderSemantic('Headers for permission operations require BOTH auth component and permission (body) component')

    try:
        auth_component: BaseAuthComponent = await process_component(n_bytes=header_component.auth_size, reader=reader, component_type='auth', timeout=SERVER_CONFIG.read_timeout)
    except asyncio.TimeoutError:
        raise SlowStreamRate
    except (asyncio.IncompleteReadError, ValidationError, orjson.JSONDecodeError):
        raise InvalidAuthSemantic
    
    if not auth_component.auth_logical_check(flag='authentication'):
        raise InvalidAuthSemantic('Permission operations require an auth component with ONLY the following: identity, token, refresh_digest')
    
    await user_master.authenticate_session(username=auth_component.identity, token=auth_component.token, raise_on_exc=True)
    if header_component.subcategory not in PermissionFlags._value2member_map_:
        raise UnsupportedOperation(f'Unsupported operation for category: {CategoryFlag.PERMISSION._name_}')
    
    # All checks at the component level passed, read file component

    permission_component: BasePermissionComponent = await process_component(n_bytes=header_component.body_size, reader=reader, component_type='permission', timeout=SERVER_CONFIG.read_timeout)
    subhandler = _PERMISSION_SUBHANDLER_MAPPING[header_component.subcategory]
    header, body = await subhandler(header_component, auth_component, permission_component)

    return header, body

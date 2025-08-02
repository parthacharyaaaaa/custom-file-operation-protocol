import asyncio
from typing import Optional, TypeAlias, Callable, Coroutine, Any
from types import MappingProxyType

from models.flags import PermissionFlags, CategoryFlag
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BasePermissionComponent
from models.response_models import ResponseHeader, ResponseBody

from server.comms_utils.incoming import process_component
from server.dependencies import ServerSingletonsRegistry
from server.errors import InvalidHeaderSemantic, InvalidAuthSemantic, SlowStreamRate, UnsupportedOperation
from server.permission_ops.permission_subhandlers import grant_permission, revoke_permission, hide_file, publicise_file, transfer_ownership

import orjson
from pydantic import ValidationError


__all__ = ('top_permission_handler', 'PERMISSION_SUBHABDLER')

PERMISSION_SUBHABDLER: TypeAlias = Callable[[BaseHeaderComponent, BaseAuthComponent, BasePermissionComponent],
                                      Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]]

_PERMISSION_SUBHANDLER_MAPPING: MappingProxyType[int, PERMISSION_SUBHABDLER] = MappingProxyType(
    dict(
        zip(
            list(PermissionFlags._member_map_.values())[:5],
            [grant_permission, revoke_permission, hide_file, publicise_file, transfer_ownership]
        )
    )
)

async def top_permission_handler(reader: asyncio.StreamReader, header_component: BaseHeaderComponent,
                                 dependency_registry: ServerSingletonsRegistry) -> tuple[ResponseHeader, Optional[ResponseBody]]:
    # Permission operations require authentication
    if not (header_component.auth_size and header_component.body_size):
        raise InvalidHeaderSemantic('Headers for permission operations require BOTH auth component and permission (body) component')

    try:
        auth_component: BaseAuthComponent = await process_component(n_bytes=header_component.auth_size, reader=reader,
                                                                    component_type='auth', timeout=dependency_registry.server_config.read_timeout)
    except asyncio.TimeoutError:
        raise SlowStreamRate
    except (asyncio.IncompleteReadError, ValidationError, orjson.JSONDecodeError):
        raise InvalidAuthSemantic
    
    if not auth_component.auth_logical_check(flag='authentication'):
        raise InvalidAuthSemantic('Permission operations require an auth component with ONLY the following: identity, token, refresh_digest')
    
    await dependency_registry.user_manager.authenticate_session(username=auth_component.identity, token=auth_component.token, raise_on_exc=True)
    if header_component.subcategory not in PermissionFlags._value2member_map_:
        raise UnsupportedOperation(f'Unsupported operation for category: {CategoryFlag.PERMISSION._name_}')
    
    # All checks at the component level passed, read permission component
    permission_component: BasePermissionComponent = await process_component(n_bytes=header_component.body_size, reader=reader,
                                                                            component_type='permission', timeout=dependency_registry.server_config.read_timeout)
    
    # For permission operations, we'll need to mask the role bits 
    subhandler = _PERMISSION_SUBHANDLER_MAPPING[header_component.subcategory & ~PermissionFlags.ROLE_EXTRACTION_BITMASK]
    prepped_subhandler = dependency_registry.inject_global_singletons(func=subhandler,
                                                                      header_component=header_component,
                                                                      auth_component=auth_component,
                                                                      permission_component=permission_component)
    
    header, body = await prepped_subhandler()
    return header, body

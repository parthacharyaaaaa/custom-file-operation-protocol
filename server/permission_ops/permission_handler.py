import asyncio
from typing import Mapping, Optional

from models.flags import PermissionFlags, CategoryFlag
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BasePermissionComponent
from models.response_models import ResponseHeader, ResponseBody

from server.comms_utils.incoming import process_component
from server.dependencies import ServerSingletonsRegistry
from server.errors import InvalidHeaderSemantic, InvalidAuthSemantic, SlowStreamRate, UnsupportedOperation
from server.typing import AuthSubhandler, SubhandlerResponse

import orjson
from pydantic import ValidationError


__all__ = ('top_permission_handler', 'PERMISSION_SUBHABDLER')


async def top_permission_handler(reader: asyncio.StreamReader,
                                 header_component: BaseHeaderComponent,
                                 dependency_registry: ServerSingletonsRegistry,
                                 subhandler_mapping: Mapping[AuthSubhandler, SubhandlerResponse]) -> tuple[ResponseHeader, Optional[ResponseBody]]:
    '''Entrypoint for handling `permission` operations over a stream. Performs authentication, validation, and dispatches to the appropriate subhandler.

    Args:
        reader (asyncio.StreamReader): Stream reader from which request components are read.
        header_component (BaseHeaderComponent): Parsed header containing sizes and metadata for auth and permission components.
        dependency_registry (ServerSingletonsRegistry): Registry providing server configuration and singleton dependencies required for handling.

    Returns:
        tuple[ResponseHeader,Optional[ResponseBody]]: Response header and optional response body resulting from the permission operation.

    Raises:
        InvalidHeaderSemantic: If either auth or permission components are missing in the header.
        SlowStreamRate: If reading the auth component times out.
        InvalidAuthSemantic: If the auth component fails validation or is malformed.
        UnsupportedOperation: If the requested permission subcategory is not supported.
    '''

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
    subhandler = subhandler_mapping[header_component.subcategory & ~PermissionFlags.ROLE_EXTRACTION_BITMASK]
    
    header, body = await subhandler(header_component=header_component,
                                    auth_component=auth_component,
                                    permission_component=permission_component)
    return header, body

import asyncio
from typing import Mapping, Optional

from models.flags import AuthFlags, CategoryFlag
from models.response_models import ResponseHeader, ResponseBody
from models.request_model import BaseHeaderComponent, BaseAuthComponent

from server.comms_utils.incoming import process_component
from server.dependencies import ServerSingletonsRegistry
from server.errors import InvalidAuthSemantic, UnsupportedOperation
from server.typing import AuthSubhandler, SubhandlerResponse

__all__ = ('top_auth_handler',)


async def top_auth_handler(reader: asyncio.StreamReader,
                           header_component: BaseHeaderComponent,
                           dependency_registry: ServerSingletonsRegistry,
                           subhandler_mapping: Mapping[AuthSubhandler, SubhandlerResponse]) -> tuple[ResponseHeader, Optional[ResponseBody]]:
    '''Entrypoint for handling `AUTH` operations over a stream. Performs authentication, validation, and dispatches to the appropriate subhandler.

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
    if not header_component.auth_size:
        raise InvalidAuthSemantic('Missing auth component in header, and no unauthenticated operation requested')

    auth_component: BaseAuthComponent = await process_component(n_bytes=header_component.auth_size, reader=reader,
                                                                component_type='auth', timeout=dependency_registry.server_config.read_timeout)

    if header_component.subcategory not in AuthFlags._value2member_map_:    # R level function name, absolutely vile.
        raise UnsupportedOperation(f'Unsupported operation for category: {CategoryFlag.AUTH._name_}')
    
    # Delegate actual handling to defined functions/coroutines
    subhandler = subhandler_mapping[header_component.subcategory]

    header, body = await subhandler(header_component=header_component,
                                    auth_component=auth_component)
    return header, body

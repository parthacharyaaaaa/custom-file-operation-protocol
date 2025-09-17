import asyncio
from typing import Mapping, Optional

from models.flags import AuthFlags, CategoryFlag
from models.response_models import ResponseHeader, ResponseBody
from models.request_model import BaseHeaderComponent, BaseAuthComponent
from models.typing import ProtocolComponent

from server.comms_utils.incoming import process_component
from server.dependencies import ServerSingletonsRegistry
from server.errors import InvalidAuthSemantic, UnsupportedOperation
from server.typing import AuthSubhandler

__all__ = ('top_auth_handler',)


async def top_auth_handler(stream_reader: asyncio.StreamReader,
                           header_component: BaseHeaderComponent,
                           server_singleton_registry: ServerSingletonsRegistry,
                           subhandler_mapping: Mapping[AuthFlags, AuthSubhandler]) -> tuple[ResponseHeader, Optional[ResponseBody]]:
    '''Entrypoint for handling `AUTH` operations over a stream. Performs authentication, validation, and dispatches to the appropriate subhandler.

    Args:
        stream_reader (asyncio.StreamReader): Stream reader from which request components are read.
        header_component (BaseHeaderComponent): Parsed header containing sizes and metadata for auth and permission components.
        server_singleton_registry (ServerSingletonsRegistry): Registry providing server configuration and singleton dependencies required for handling.

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

    auth_component: ProtocolComponent  = await process_component(n_bytes=header_component.auth_size,
                                                                 reader=stream_reader,
                                                                 component_type='auth',
                                                                 timeout=server_singleton_registry.server_config.read_timeout)
    assert isinstance(auth_component, BaseAuthComponent) 

    if header_component.subcategory not in AuthFlags._value2member_map_:    # R level function name, absolutely vile.
        raise UnsupportedOperation(f'Unsupported operation for category: {CategoryFlag.AUTH._name_}')
    
    # Delegate actual handling to defined functions/coroutines
    assert isinstance(header_component.subcategory, AuthFlags)
    subhandler = subhandler_mapping[header_component.subcategory]

    header, body = await subhandler(header_component=header_component,
                                    auth_component=auth_component)
    return header, body

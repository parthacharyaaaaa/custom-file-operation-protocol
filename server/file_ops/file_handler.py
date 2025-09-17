import asyncio
from typing import Mapping, Optional

from models.flags import FileFlags, CategoryFlag
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BaseFileComponent
from models.response_models import ResponseHeader, ResponseBody
from models.typing import ProtocolComponent

from server.comms_utils.incoming import process_component
from server.dependencies import ServerSingletonsRegistry
from server.errors import InvalidHeaderSemantic, InvalidAuthSemantic, SlowStreamRate, UnsupportedOperation
from server.typing import FileSubhandler

import orjson
from pydantic import ValidationError

__all__ = ('top_file_handler',)

async def top_file_handler(stream_reader: asyncio.StreamReader,
                           header_component: BaseHeaderComponent,
                           server_singleton_registry: ServerSingletonsRegistry,
                            subhandler_mapping: Mapping[FileFlags, FileSubhandler]) -> tuple[ResponseHeader, Optional[ResponseBody]]:
    '''Entrypoint for handling `file` operations over a stream. Performs authentication, validation, and dispatches to the appropriate subhandler.

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
    # File operations require authentication
    if not (header_component.auth_size and header_component.body_size):
        raise InvalidHeaderSemantic('Headers for permission operations require BOTH auth component and permission (body) component')

    try:
        auth_component: ProtocolComponent = await process_component(n_bytes=header_component.auth_size,
                                                                    reader=stream_reader,
                                                                    component_type='auth',
                                                                    timeout=server_singleton_registry.server_config.read_timeout)
        assert isinstance(auth_component, BaseAuthComponent) and auth_component.token
    except asyncio.TimeoutError:
        raise SlowStreamRate
    except (asyncio.IncompleteReadError, ValidationError, orjson.JSONDecodeError):
        raise InvalidAuthSemantic
    
    if not auth_component.auth_logical_check(flag='authentication'):
        raise InvalidAuthSemantic('File operations require an auth component with ONLY the following: identity, token, refresh_digest')
    
    await server_singleton_registry.user_manager.authenticate_session(username=auth_component.identity, token=auth_component.token, raise_on_exc=True)
    if header_component.subcategory not in FileFlags._value2member_map_:
        raise UnsupportedOperation(f'Unsupported operation for category: {CategoryFlag.FILE_OP._name_}')
    
    # All checks at the component level passed, read and process file component
    file_component: ProtocolComponent = await process_component(n_bytes=header_component.body_size,
                                                                reader=stream_reader,
                                                                component_type='file',
                                                                timeout=server_singleton_registry.server_config.read_timeout)
    assert isinstance(file_component, BaseFileComponent) and isinstance(header_component.subcategory, FileFlags)

    subhandler: FileSubhandler = subhandler_mapping[header_component.subcategory]
    
    header, body = await subhandler(header_component=header_component,
                                    auth_component=auth_component,
                                    file_component=file_component)
    return header, body

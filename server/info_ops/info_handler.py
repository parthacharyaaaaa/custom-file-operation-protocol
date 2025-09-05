import asyncio
from typing import Mapping, Optional

from models.constants import UNAUTHENTICATED_INFO_OPERATIONS
from models.flags import CategoryFlag, InfoFlags
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BaseInfoComponent
from models.response_models import ResponseHeader, ResponseBody

from server.comms_utils.incoming import process_component
from server.dependencies import ServerSingletonsRegistry
from server.errors import InvalidAuthSemantic, UnsupportedOperation, InvalidHeaderSemantic, SlowStreamRate, InvalidBodyValues
from server.typing import InfoSubhandler, SubhandlerResponse

import orjson
import pydantic

__all__ = ('top_info_handler',)

async def top_info_handler(reader: asyncio.StreamReader,
                           header_component: BaseHeaderComponent,
                           dependency_registry: ServerSingletonsRegistry,
                           subhandler_mapping: Mapping[InfoSubhandler, SubhandlerResponse]) -> tuple[ResponseHeader, Optional[ResponseBody]]:
    '''Entrypoint for handling `info` operations over a stream. Performs optional authentication, validation, and finally dispatches to the appropriate subhandler.

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
    if header_component.subcategory not in InfoFlags._value2member_map_:
        raise UnsupportedOperation(f'Unsupported operation (bits: {header_component.subcategory}) for category: {CategoryFlag.INFO._name_}')
    
    auth_component: BaseAuthComponent = None
    info_component: BaseInfoComponent = None
    if header_component.subcategory not in UNAUTHENTICATED_INFO_OPERATIONS:
        if not header_component.auth_size:
            raise InvalidHeaderSemantic(f'Headers for INFO operation {InfoFlags(header_component.subcategory)} require authentication')
        try:
            auth_component = await process_component(n_bytes=header_component.auth_size, reader=reader,
                                                     component_type='auth', timeout=dependency_registry.server_config.read_timeout)
        except asyncio.TimeoutError:
            raise SlowStreamRate
        except (asyncio.IncompleteReadError, pydantic.ValidationError, orjson.JSONDecodeError):
            raise InvalidAuthSemantic
    
        await dependency_registry.user_manager.authenticate_session(username=auth_component.identity, token=auth_component.token, raise_on_exc=True)
    if header_component.body_size:
        try:
            info_component = await process_component(n_bytes=header_component.body_size, reader=reader,
                                                    component_type='info', timeout=dependency_registry.server_config.read_timeout)
        except asyncio.TimeoutError:
            raise SlowStreamRate
        except (asyncio.IncompleteReadError, pydantic.ValidationError, orjson.JSONDecodeError):
            raise InvalidBodyValues

    # Subcategory bits may also contain addiitonal modifiers, such as the optional verbose bit.
    # These will need to be masked before mapping to the appropriate subhandler
    subhandler = subhandler_mapping[header_component.subcategory & InfoFlags.OPERATION_EXTRACTION_BITS]
    
    header, body = await subhandler(header_component=header_component,
                                    auth_component=auth_component,
                                    info_component=info_component)
    return header, body

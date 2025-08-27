import asyncio
from typing import Optional, TypeAlias, Callable, Coroutine, Any
from types import MappingProxyType

from models.constants import UNAUTHENTICATED_INFO_OPERATIONS
from models.flags import CategoryFlag, InfoFlags
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BasePermissionComponent, BaseInfoComponent
from models.response_models import ResponseHeader, ResponseBody

from server.comms_utils.incoming import process_component
from server.dependencies import ServerSingletonsRegistry
from server.errors import InvalidAuthSemantic, UnsupportedOperation, InvalidHeaderSemantic, SlowStreamRate, InvalidBodyValues
from server.info_ops.info_subhandlers import handle_heartbeat, handle_permission_query, handle_filedata_query, handle_user_query, handle_storage_query, handle_ssl_query

import orjson
import pydantic

__all__ = ('top_info_handler', 'INFO_SUBHANDLER')

INFO_SUBHANDLER: TypeAlias = Callable[[BaseHeaderComponent, BaseAuthComponent, BasePermissionComponent],
                                      Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]]

INFO_SUBHANDLER_MAPPING: MappingProxyType[int, INFO_SUBHANDLER] = MappingProxyType(
    {
        InfoFlags.HEARTBEAT : handle_heartbeat,
        InfoFlags.PERMISSION_METADATA : handle_permission_query,
        InfoFlags.FILE_METADATA : handle_filedata_query,
        InfoFlags.USER_METADATA : handle_user_query,
        InfoFlags.STORAGE_USAGE : handle_storage_query,
        InfoFlags.SSL_CREDENTIALS : handle_ssl_query
    }
)

async def top_info_handler(reader: asyncio.StreamReader,
                           header_component: BaseHeaderComponent,
                           dependency_registry: ServerSingletonsRegistry) -> tuple[ResponseHeader, Optional[ResponseBody]]:
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
    subhandler = INFO_SUBHANDLER_MAPPING[header_component.subcategory & InfoFlags.OPERATION_EXTRACTION_BITS]
    prepped_subhandler = dependency_registry.inject_global_singletons(func=subhandler,
                                                                      header_component=header_component,
                                                                      auth_component=auth_component,
                                                                      info_component=info_component)
    
    header, body = await prepped_subhandler()
    return header, body

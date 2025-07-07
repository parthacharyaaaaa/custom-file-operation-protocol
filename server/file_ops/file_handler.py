import asyncio
from typing import Optional, TypeAlias, Callable, Coroutine, Any
from types import MappingProxyType

from models.flags import FileFlags, CategoryFlag
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BaseFileComponent
from models.response_models import ResponseHeader, ResponseBody

from server.bootup import user_master
from server.comms_utils.incoming import process_component
from server.errors import InvalidHeaderSemantic, InvalidAuthSemantic, SlowStreamRate, UnsupportedOperation
from server.file_ops.operations import create_file, read_file, write_file, append_file, delete_file

import orjson
from pydantic import ValidationError


FILE_SUBHANDLERS: TypeAlias = Callable[[BaseHeaderComponent, BaseAuthComponent, BaseFileComponent],
                                      Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]]

_FILE_SUBHANDLER_MAPPING: MappingProxyType[int, FILE_SUBHANDLERS] = MappingProxyType(
    dict(
        zip(
            FileFlags._member_names_,
            [create_file, read_file, write_file, append_file, delete_file]
        )
    )
)


async def top_file_handler(reader: asyncio.StreamReader, header_component: BaseHeaderComponent) -> tuple[ResponseHeader, Optional[ResponseBody]]:
    # File operations require authentication
    if not (header_component.auth_size and header_component.body_size):
        raise InvalidHeaderSemantic('Headers for permission operations require BOTH auth component and permission (body) component')

    try:
        auth_component: BaseAuthComponent = await process_component(n_bytes=header_component.auth_size, reader=reader, component_type='auth')
    except asyncio.TimeoutError:
        raise SlowStreamRate
    except (asyncio.IncompleteReadError, ValidationError, orjson.JSONDecodeError):
        raise InvalidAuthSemantic
    
    if not auth_component.auth_logical_check(flag='authentication'):
        raise InvalidAuthSemantic('File operations require an auth component with ONLY the following: identity, token, refresh_digest')
    
    user_master.authenticate_session(username=auth_component.identity, token=auth_component.token, raise_on_exc=True)
    if header_component.subcategory not in FileFlags._value2member_map_:
        raise UnsupportedOperation(f'Unsupported operation for category: {CategoryFlag.FILE_OP._name_}')
    
    # All checks at the component level passed, read and process file component
    file_component: BaseFileComponent = await process_component(n_bytes=header_component.body_size, reader=reader, component_type='file')
    subhandler = _FILE_SUBHANDLER_MAPPING[header_component.subcategory]
    header, body = await subhandler(header_component, auth_component, file_component)

    return header, body

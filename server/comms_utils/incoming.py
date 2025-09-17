'''Utils for incoming streams from client to server'''
import asyncio
from typing import Any, Optional, TypeVar
from types import MappingProxyType

from models.request_model import BaseHeaderComponent, BaseAuthComponent, BaseFileComponent, BasePermissionComponent, BaseInfoComponent
from models.flags import CategoryFlag

import server.errors as exc

from pydantic import BaseModel, ValidationError
import orjson

__all__ = ('CATEGORY_MODEL_MAP', 'serialize_json', 'parse_body', 'process_component')

T = TypeVar('T', BaseHeaderComponent, BaseAuthComponent, BaseFileComponent, BasePermissionComponent, BaseInfoComponent)

CATEGORY_MODEL_MAP: MappingProxyType[int, type[BaseModel]] = MappingProxyType({CategoryFlag.AUTH: BaseAuthComponent,
                                                                               CategoryFlag.FILE_OP: BaseFileComponent,
                                                                               CategoryFlag.PERMISSION: BasePermissionComponent})

async def serialize_json(data: bytes, awaitable_lower_bound: int = 2048, await_timeout: float = 5) -> dict[str, Any]:
    '''Deserialize JSON bytes into a Python dictionary, using async thread offloading for large payloads.

    Args:
        data (bytes): JSON-encoded data to deserialize.
        awaitable_lower_bound (int): Size in bytes above which deserialization is offloaded to a separate thread, defaults to 2048.
        await_timeout (float): Maximum time in seconds to wait for async deserialization, defaults to 5.

    Returns:
        dict[str,Any]: Python dictionary resulting from deserialization.
    '''
    if len(data) < awaitable_lower_bound:
        return orjson.loads(data)
    return await asyncio.wait_for(asyncio.to_thread(orjson.loads(data)), timeout=await_timeout)

async def parse_body(header: BaseHeaderComponent, body: bytes) -> BaseModel:
    '''Parse the request body into the appropriate Pydantic model based on the header category.

    Args:
        header (BaseHeaderComponent): Header component containing metadata, including the category.
        body (bytes): Raw request body to be parsed.

    Returns:
        BaseModel: Instance of the model corresponding to the header's category, populated with the body data.

    Raises:
        ValueError: If the header's category is unsupported.
    '''

    component_cls: Optional[type[BaseModel]] = CATEGORY_MODEL_MAP.get(header.category)
    if not component_cls:
        raise ValueError('Unsupported category')
    
    body_mapping: dict[str, Any] = await serialize_json(body)
    return component_cls.model_validate(body_mapping)

async def process_component(n_bytes: int,
                            reader: asyncio.StreamReader,
                            component_type: type[T], timeout: float) -> T:
    '''Read and process a specific request component from a stream.

    Args:
        n_bytes (int): Number of bytes to read from the stream for this component.
        reader (asyncio.StreamReader): Stream reader to read the component from.
        component_type (ProtocolComponent): Type of component being processed.
        timeout (float): Maximum time in seconds to wait for the component to be read.

    Returns:
        RequestComponentType: Parsed request component object corresponding to the specified type.

    Raises:
        SlowStreamRate: If the stream is too slow or times out.
        InvalidHeaderSemantic: If the component cannot be parsed or fails validation.
    '''
    try:
        raw_component: bytes = await asyncio.wait_for(reader.readexactly(n_bytes), timeout)
        return component_type.model_validate_json(raw_component)
    
    except (asyncio.IncompleteReadError, ValidationError, orjson.JSONDecodeError) as e:
        if isinstance(e, asyncio.IncompleteReadError) and e.partial == b'':
            raise exc.SlowStreamRate
        
        raise exc.InvalidHeaderSemantic
    except asyncio.TimeoutError:
        raise exc.SlowStreamRate
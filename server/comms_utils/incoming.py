'''Utils for incoming streams from client to server'''
import asyncio
from typing import Any, Literal
from types import MappingProxyType

from models.request_model import BaseHeaderComponent, BaseAuthComponent, BaseFileComponent, BasePermissionComponent, BaseInfoComponent, RequestComponentType
from models.flags import CategoryFlag

import server.errors as exc

from pydantic import BaseModel, ValidationError
import orjson

__all__ = ('CATEGORY_MODEL_MAP', 'serialize_json', 'parse_body', 'process_component')

CATEGORY_MODEL_MAP: MappingProxyType[int, type[BaseModel]] = MappingProxyType({CategoryFlag.AUTH: BaseAuthComponent,
                                                                               CategoryFlag.FILE_OP: BaseFileComponent,
                                                                               CategoryFlag.PERMISSION: BasePermissionComponent})

async def serialize_json(data: bytes, awaitable_lower_bound: int = 2048, await_timeout: float = 5) -> dict[str, Any]:
    if len(data) < awaitable_lower_bound:
        return orjson.loads(data)
    return await asyncio.wait_for(asyncio.to_thread(orjson.loads(data)), timeout=await_timeout)

async def parse_body(header: BaseHeaderComponent, body: bytes) -> BaseModel:
    component_cls: type[BaseModel] = CATEGORY_MODEL_MAP.get(header.category)
    if not component_cls:
        raise ValueError('Unsupported category')
    
    body_mapping: dict[str, Any] = await serialize_json(body)
    return component_cls.model_validate(body_mapping)

async def process_component(n_bytes: int, reader: asyncio.StreamReader, component_type: Literal['header', 'auth', 'file', 'permission', 'info'], timeout: float) -> RequestComponentType:
    model = None
    if component_type == 'header':
        model = BaseHeaderComponent
    elif component_type == 'auth':
        model = BaseAuthComponent
    elif component_type == 'file':
        model = BaseFileComponent
    elif component_type == 'permission':
        model = BasePermissionComponent
    elif component_type == 'info':
        model = BaseInfoComponent
    try:
        raw_component: bytes = await asyncio.wait_for(reader.readexactly(n_bytes), timeout)
        return model.model_validate_json(raw_component)
    
    except (asyncio.IncompleteReadError, ValidationError, orjson.JSONDecodeError) as e:
        if isinstance(e, asyncio.IncompleteReadError) and e.partial == b'':
            raise exc.SlowStreamRate
        
        raise exc.InvalidHeaderSemantic
    except asyncio.TimeoutError:
        raise exc.SlowStreamRate
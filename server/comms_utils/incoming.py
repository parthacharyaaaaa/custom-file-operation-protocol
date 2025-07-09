'''Utils for incoming streams from client to server'''
import asyncio
from typing import Any, Literal
from types import MappingProxyType

from models.request_model import BaseHeaderComponent, BaseAuthComponent, BaseFileComponent, BasePermissionComponent, RequestComponentType
from models.flags import CategoryFlag

from server.config.server_config import SERVER_CONFIG
import server.errors as exc

from pydantic import BaseModel, ValidationError
import orjson

CATEGORY_MODEL_MAP: MappingProxyType[int, type[BaseModel]] = MappingProxyType({CategoryFlag.AUTH: BaseAuthComponent, CategoryFlag.FILE_OP: BaseFileComponent, CategoryFlag.PERMISSION: BasePermissionComponent})

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

async def process_component(n_bytes: int, reader: asyncio.StreamReader, component_type: Literal['header', 'auth', 'file', 'permission']) -> RequestComponentType:
    model, timeout = None, None
    if component_type == 'header':
        model, timeout = BaseHeaderComponent, SERVER_CONFIG.read_timeout
    elif component_type == 'auth':
        model, timeout = BaseAuthComponent, SERVER_CONFIG.read_timeout
    elif component_type == 'file':
        model, timeout = BaseFileComponent, SERVER_CONFIG.read_timeout
    elif component_type == 'permission':
        model, timeout = BasePermissionComponent, SERVER_CONFIG.read_timeout
    
    try:
        raw_component: bytes = await asyncio.wait_for(reader.readexactly(n_bytes), timeout)
        component_mapping: dict[str, Any] = await serialize_json(raw_component)
        return model.model_validate_json(component_mapping)
    
    except (asyncio.IncompleteReadError, ValidationError, orjson.JSONDecodeError):
        raise exc.InvalidHeaderSemantic
    except asyncio.TimeoutError:
        raise exc.SlowStreamRate
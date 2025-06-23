import asyncio
from server.config import CategoryFlag
from server.models.request_model import BaseAuthComponent, BaseFileComponent, BasePermissionComponent, BaseHeaderComponent
from pydantic import BaseModel
import orjson
from typing import Any
from types import MappingProxyType

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
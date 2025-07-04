'''Utils for incoming streams from client to server'''
import asyncio
from pydantic import ValidationError
import server.errors as exc
from server.config import ServerConfig
from server.models.request_model import BaseHeaderComponent, BaseAuthComponent, BaseFileComponent, BasePermissionComponent, RequestComponentType
from server.parsers import serialize_json
from typing import Any, Literal
import orjson

async def process_component(n_bytes: int, reader: asyncio.StreamReader, component_type: Literal['header', 'auth', 'file', 'permission']) -> RequestComponentType:
    model, timeout = None, None
    if component_type == 'header':
        model, timeout = BaseHeaderComponent, ServerConfig.HEADER_READ_TIMEOUT.value
    elif component_type == 'auth':
        model, timeout = BaseAuthComponent, ServerConfig.AUTH_READ_TIMEOUT.value
    elif component_type == 'file':
        model, timeout = BaseFileComponent, ServerConfig.FILE_READ_TIMEOUT.value
    elif component_type == 'permission':
        model, timeout = BasePermissionComponent, ServerConfig.PERMISSION_READ_TIMEOUT.value
    
    try:
        raw_component: bytes = await asyncio.wait_for(reader.readexactly(n_bytes), timeout)
        component_mapping: dict[str, Any] = await serialize_json(raw_component)
        return model.model_validate_json(component_mapping)
    
    except (asyncio.IncompleteReadError, ValidationError, orjson.JSONDecodeError):
        raise exc.InvalidHeaderSemantic
    except asyncio.TimeoutError:
        raise exc.SlowStreamRate
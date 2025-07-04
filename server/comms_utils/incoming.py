'''Utils for incoming streams from client to server'''
import asyncio
from pydantic import ValidationError
import server.errors as exc
from server.config import ServerConfig
import server.models.request_model as req_models
from server.parsers import serialize_json
from typing import Any, Optional
import orjson

async def process_header(n_bytes: int, reader: asyncio.StreamReader) -> Optional[req_models.BaseHeaderComponent]:
    try:
        raw_header: bytes = await asyncio.wait_for(reader.readexactly(n_bytes), timeout=ServerConfig.HEADER_READ_TIMEOUT.value)
        header: dict[str, Any] = await serialize_json(raw_header)
        return req_models.BaseHeaderComponent.model_validate(obj=header)
    except (asyncio.IncompleteReadError, ValidationError, orjson.JSONDecodeError):
        raise exc.InvalidHeaderSemantic
    except asyncio.TimeoutError:
        raise exc.SlowStreamRate
    
async def process_auth(n_bytes: int, reader: asyncio.StreamReader) -> req_models.BaseAuthComponent:
    raw_auth: bytes = await asyncio.wait_for(reader.readexactly(n_bytes), timeout=ServerConfig.AUTH_READ_TIMEOUT.value)
    auth_mapping: dict[str, Any] = await serialize_json(raw_auth)
    return req_models.BaseAuthComponent.model_validate_json(auth_mapping)

'''Utils for incoming streams from client to server'''

import asyncio
from pydantic import ValidationError
import server.errors as exc
from server.config import ServerConfig
import server.models.request_model as req_models
import server.models.response_models as res_models
from server.parsers import serialize_json
from typing import Any
from orjson import JSONDecodeError

async def process_header(n_bytes: int, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> req_models.BaseHeaderComponent:
    exception: bool = False
    try:
        raw_header: bytes = await asyncio.wait_for(reader.readexactly(ServerConfig.HEADER_READ_BYTESIZE), timeout=ServerConfig.HEADER_READ_TIMEOUT)
        header: dict[str, Any] = await serialize_json(raw_header)
        return req_models.BaseHeaderComponent.model_validate(obj=header)
    except (asyncio.IncompleteReadError, ValidationError, JSONDecodeError):
        exception = True
        response: res_models.ResponseHeader = res_models.ResponseHeader.from_unverifiable_header(exc.InvalidHeaderSemantic, version=ServerConfig.VERSION)
    except asyncio.TimeoutError:
        exception = True
        response: res_models.ResponseHeader = res_models.ResponseHeader.from_unverifiable_header(exc.SlowStreamRate, version=ServerConfig.VERSION)
    
    # Control would only come here in case of an exception
    writer.write(response.model_dump_json(warnings='error'))
    writer.write_eof()
    await writer.drain()
    writer.close()
    await writer.wait_closed()

    return None
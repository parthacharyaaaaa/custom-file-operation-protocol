import asyncio
from typing import Optional, Literal
from models.response_models import ResponseHeader, ResponseBody
from models.constants import RESPONSE_CONSTANTS

READ_LOCK: asyncio.Lock = asyncio.Lock()

async def process_response(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                           timeout: float, lock_contention_timmeout: float = 3.0) -> tuple[ResponseHeader, Optional[ResponseBody]]:
    acquired: Literal[True] = await asyncio.wait_for(READ_LOCK.acquire(), lock_contention_timmeout)
    try:
        raw_header: bytes = await asyncio.wait_for(reader.readexactly(RESPONSE_CONSTANTS.header.bytesize), timeout)
        response_header: ResponseHeader = ResponseHeader.model_validate_json(raw_header)
        response_body: ResponseBody = None
        if response_header.body_size:
            raw_body = await asyncio.wait_for(reader.readexactly(response_header.body_size), timeout)
            response_body = ResponseBody.model_validate_json(raw_body)
    finally:
        READ_LOCK.release()

    if response_header.ended_connection:
        writer.close()
        await writer.wait_closed()
    
    return response_header, response_body
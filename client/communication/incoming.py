import asyncio
from typing import Optional
from models.response_models import ResponseHeader, ResponseBody
from models.constants import RESPONSE_CONSTANTS

async def process_response(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, timeout: float, header_bytesize: Optional[int] = None) -> tuple[ResponseHeader, Optional[ResponseBody]]:
    raw_header: bytes = await asyncio.wait_for(reader.readexactly(header_bytesize or RESPONSE_CONSTANTS.header.bytesize), timeout)

    response_header: ResponseHeader = ResponseHeader.model_validate_json(raw_header)
    response_body: ResponseBody = None
    if response_header.body_size:
        raw_body = await asyncio.wait_for(reader.readexactly(response_header.body_size), timeout)
        response_body = ResponseBody.model_validate_json(raw_body)
    
    if response_header.ended_connection:
        writer.close()
        await writer.wait_closed()
    
    return response_header, response_body
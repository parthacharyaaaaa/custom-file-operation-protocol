'''Outgoing messages from server to client'''
import asyncio
from models.request_model import BaseHeaderComponent
from models.response_models import ResponseHeader, ResponseBody
from typing import Optional, Union

async def send_heartbeat(header: BaseHeaderComponent) -> tuple[ResponseBody, None]:
    '''Send a heartbeat signal back to the client'''
    return (
        ResponseHeader(version=header.version, code='1:hb', description='Doki Doki', ended_connection=header.finish),
        None
    )

async def send_response(writer: asyncio.StreamWriter, response: Union[ResponseHeader, bytes], body: Optional[Union[ResponseBody, bytes]] = None) -> None:
    header_stream: bytes = response if isinstance(response, bytes) else response.as_bytes()
    if isinstance(response, bytes):
        writer.write(header_stream)
    if body:
        body_stream: bytes = body if isinstance(body, bytes) else body.as_bytes()
        writer.write(body_stream)
        
    await writer.drain()
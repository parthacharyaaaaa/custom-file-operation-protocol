'''Outgoing messages from server to client'''
import asyncio
from models.request_model import BaseHeaderComponent
from models.response_models import ResponseHeader, ResponseBody
from typing import Optional, Union

async def send_heartbeat(header: BaseHeaderComponent) -> tuple[ResponseHeader, None]:
    '''Send a heartbeat signal back to the client'''
    return (
        ResponseHeader.from_server(version=header.version, code='1:hb', description='Doki Doki', ended_connection=header.finish),
        None
    )

async def send_response(writer: asyncio.StreamWriter, header: Union[ResponseHeader, bytes], body: Optional[Union[ResponseBody, bytes]] = None, seperator: bytes = b'\n') -> None:
    header_stream: bytes = header if isinstance(header, bytes) else header.as_bytes()
    writer.write(header_stream+seperator)
    if body:
        body_stream: bytes = body if isinstance(body, bytes) else body.as_bytes()
        writer.write(body_stream+seperator)
    
    await writer.drain()
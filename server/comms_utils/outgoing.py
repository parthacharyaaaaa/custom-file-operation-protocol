'''Outgoing messages from server to client'''
import asyncio
from models.request_model import BaseHeaderComponent
from models.response_models import ResponseHeader, ResponseBody
from typing import Optional, Union
from server.config.server_config import SERVER_CONFIG

async def send_heartbeat(header: BaseHeaderComponent) -> tuple[ResponseHeader, None]:
    '''Send a heartbeat signal back to the client'''
    return (
        ResponseHeader(version=header.version, code='1:hb', description='Doki Doki', ended_connection=header.finish, responder_hostname=SERVER_CONFIG.host, responder_port=SERVER_CONFIG.port),
        None
    )

async def send_response(writer: asyncio.StreamWriter, header: Union[ResponseHeader, bytes], body: Optional[Union[ResponseBody, bytes]] = None) -> None:
    header_stream: bytes = header if isinstance(header, bytes) else header.as_bytes()
    if isinstance(header, bytes):
        writer.write(header_stream)
    if body:
        body_stream: bytes = body if isinstance(body, bytes) else body.as_bytes()
        writer.write(body_stream)
    
    await writer.drain()
'''Outgoing messages from server to client'''
import asyncio
from typing import Optional, Union

from models.request_model import BaseHeaderComponent
from models.response_models import ResponseHeader, ResponseBody
from models.constants import RESPONSE_CONSTANTS
from models.response_codes import SuccessFlags

from server.dependencies import ServerSingletonsRegistry

__all__ = ('send_heartbeat', 'send_response')

async def send_heartbeat(reader: asyncio.StreamReader, header: BaseHeaderComponent, dependency_registry: ServerSingletonsRegistry) -> tuple[ResponseHeader, None]:
    '''Send a heartbeat signal back to the client'''
    return (
        ResponseHeader.from_server(config=dependency_registry.server_config, code=SuccessFlags.HEARTBEAT.value, version=header.version, ended_connection=header.finish),
        None
    )

async def send_response(writer: asyncio.StreamWriter, header: Union[ResponseHeader, bytes], body: Optional[Union[ResponseBody, bytes]] = None, seperator: Optional[bytes] = b'') -> None:
    header_stream: bytes = header if isinstance(header, bytes) else header.as_bytes()
    # Header is of constant size, given by RESPONSE_CONSTANTS.header.bytesize. Smaller headers will need to be padded
    header_stream += b' ' * (RESPONSE_CONSTANTS.header.bytesize - len(header_stream))
    writer.write(header_stream + seperator)
    if body:
        body_stream: bytes = body if isinstance(body, bytes) else body.as_bytes()
        writer.write(body_stream + seperator)
    
    await writer.drain()
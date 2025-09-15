'''Outgoing messages from server to client'''
import asyncio
from typing import Optional, Union

from models.response_models import ResponseHeader, ResponseBody
from models.constants import RESPONSE_CONSTANTS

__all__ = ('send_response',)

async def send_response(writer: asyncio.StreamWriter,
                        header: Union[ResponseHeader, bytes],
                        body: Optional[Union[ResponseBody, bytes]] = None,
                        seperator: bytes = b'') -> None:
    '''Send a response over a stream, including header and optional body, with optional separators.
    
    Args:
        writer (asyncio.StreamWriter): Stream writer to send the response through.
        header (Union[ResponseHeader,bytes]): Response header, either as an object or raw bytes.
        body (Optional[Union[ResponseBody,bytes]]): Optional response body, either as an object or raw bytes.
        seperator (Optional[bytes]): Optional byte sequence to append after header and body, defaults to b''.

    Returns:
        None
    '''
    
    header_stream: bytes = header.as_bytes() if isinstance(header, ResponseHeader) else bytes(header)
    # Header is of constant size, given by RESPONSE_CONSTANTS.header.bytesize. Smaller headers will need to be padded
    header_stream += b' ' * (RESPONSE_CONSTANTS.header.bytesize - len(header_stream))
    writer.write(header_stream + seperator)
    if body:
        body_stream: bytes = body.as_bytes() if isinstance(body, ResponseBody) else bytes(body)
        writer.write(body_stream + seperator)
    
    await writer.drain()
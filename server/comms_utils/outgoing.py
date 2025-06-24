'''Outgoing messages from server to client'''
import asyncio
from server.models.request_model import BaseHeaderComponent

async def send_heartbeat(header: BaseHeaderComponent, writer: asyncio.StreamWriter, close_conn: bool = False) -> None:
    '''Send a heartbeat signal back to the client'''
    writer.write(b'{"heartbeat" : "doki doki"}\n')
    await writer.drain()
    if close_conn:
        writer.write_eof()
        writer.close()
        await writer.wait_closed()
    return
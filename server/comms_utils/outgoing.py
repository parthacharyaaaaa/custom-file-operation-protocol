'''Outgoing messages from server to client'''
import asyncio
from server.models.request_model import BaseHeaderComponent
from server.models.response_models import ResponseHeader
import orjson

async def send_heartbeat(header: BaseHeaderComponent, writer: asyncio.StreamWriter, close_conn: bool = False) -> None:
    '''Send a heartbeat signal back to the client'''
    writer.write(orjson.dumps(ResponseHeader.make_response_header(header.version, '1:hb', description="Doki Doki").model_dump_json()))
    await writer.drain()
    if close_conn:
        writer.write_eof()
        writer.close()
        await writer.wait_closed()
    return
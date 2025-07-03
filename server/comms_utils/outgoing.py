'''Outgoing messages from server to client'''
import asyncio
import orjson
from server.models.request_model import BaseHeaderComponent
from server.models.response_models import ResponseHeader, ResponseBody
from typing import Optional

async def send_heartbeat(header: BaseHeaderComponent, writer: asyncio.StreamWriter, close_conn: bool = False) -> None:
    '''Send a heartbeat signal back to the client'''
    writer.write(orjson.dumps(ResponseHeader.make_response_header(header.version, '1:hb', description="Doki Doki").model_dump_json()))
    await writer.drain()
    if close_conn:
        writer.write_eof()
        writer.close()
        await writer.wait_closed()
    return

async def send_response(writer: asyncio.StreamWriter, response: ResponseHeader, body: Optional[ResponseBody] = None, close_conn: bool = False) -> None:
    writer.write(orjson.dumps(response.model_dump()))
    if body:
        writer.write(orjson.dump(body.model_dump()))
    await writer.drain()
    if close_conn:
        writer.write_eof()
        await writer.drain()
        writer.close()
        await writer.wait_closed()
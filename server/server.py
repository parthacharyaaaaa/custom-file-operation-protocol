import asyncio
from functools import partial
from types import FunctionType
from server import response_codes
from server.config import ServerConfig, CategoryFlag
from server.authz.session_master import SessionMaster
from server.models.request_model import BaseHeaderComponent
from server.models.response_models import ResponseHeader
from server.comms_utils.incoming import process_header
from server.comms_utils.outgoing import send_heartbeat
from server.dispatch import TOP_LEVEL_REQUEST_MAPPING
from server.errors import UnsupportedOperation
import orjson

async def callback(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_master: SessionMaster) -> None:
    header_component: BaseHeaderComponent = await process_header(ServerConfig.HEADER_READ_BYTESIZE.value, reader, writer)
    if not header_component:
        return
    
    # TODO: Add early on logic to terminate user sessions on header_component.finish being True
    # On heartbeat signal, return early
    if header_component.category == CategoryFlag.HEARTBEAT:
        return await send_heartbeat(header_component, writer, close_conn=header_component.finish)
    
    handler: FunctionType = TOP_LEVEL_REQUEST_MAPPING.get(header_component.category)
    if not handler:
        writer.write(orjson.dumps(
            ResponseHeader
            .from_protocol_exception(UnsupportedOperation, context_request=header_component, end_conn=header_component.finish)
            .model_dump_json()))
        await writer.drain()
        if header_component.finish:
            writer.write_eof()
            await writer.drain()
            writer.close()
            return await writer.wait_closed()
    
    await handler()

async def main() -> None:
    if not response_codes:
        raise RuntimeError('No response codes found, server cannot start...')
    
    session_master: SessionMaster = SessionMaster()
    server: asyncio.Server = await asyncio.start_server(client_connected_cb=partial(callback, session_master=session_master),
                                                        host=ServerConfig.HOST.value, port=ServerConfig.PORT.value)
    async with server:
        await server.serve_forever()

asyncio.run(main())
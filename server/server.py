import asyncio
import os
from functools import partial
from types import FunctionType
from psycopg.conninfo import make_conninfo
from server import response_codes
from server.config import ServerConfig
from server.models.request_model import BaseHeaderComponent
from server.models.response_models import ResponseHeader
from server.comms_utils.incoming import process_header
from server.dispatch import TOP_LEVEL_REQUEST_MAPPING
from server.errors import UnsupportedOperation, InternalServerError, SlowStreamRate
from server.bootup import init_connection_master, init_session_master, init_file_lock
import orjson

async def callback(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        header_component: BaseHeaderComponent = await process_header(ServerConfig.HEADER_READ_BYTESIZE.value, reader, writer)
        if not header_component:
            raise SlowStreamRate
        
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
        
        await handler(header_component)
    except:
        # Unhandled exceptions
        writer.write(orjson.dumps(
            ResponseHeader.from_unverifiable_data(InternalServerError)
            .model_dump_json()
        ))
        return await writer.drain()

async def main() -> None:
    # Check runtime dependencies
    if not response_codes:
        raise RuntimeError('No response codes found, server cannot start...')
    
    # Initialize all extensions that the server depends on
    init_session_master(ServerConfig)
    init_connection_master(
        make_conninfo(user=os.environ['PG_USERNAME'], password=os.environ['PG_PASSWORD'],
                      host=os.environ['PG_HOST'], port=os.environ['PG_PORT'], dbname=os.environ['PG_DBNAME']))
    init_file_lock()

    # Start server
    server: asyncio.Server = await asyncio.start_server(client_connected_cb=partial(callback),
                                                        host=ServerConfig.HOST.value, port=ServerConfig.PORT.value)
    async with server:
        await server.serve_forever()

asyncio.run(main())
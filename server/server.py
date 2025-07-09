import asyncio
import os
import sys
import orjson
from typing import Optional, Any, Coroutine, Callable

from models.flags import CategoryFlag
from models.request_model import BaseHeaderComponent
from models.response_models import ResponseHeader, ResponseBody
from models.constants import REQUEST_CONSTANTS

from psycopg.conninfo import make_conninfo
from server.bootup import init_connection_master, init_user_master, init_file_lock, init_caches, init_logger
from server.comms_utils.incoming import process_component
from server.comms_utils.outgoing import send_response
from server.config.server_config import SERVER_CONFIG
from server.dispatch import TOP_LEVEL_REQUEST_MAPPING
from server.errors import ProtocolException, UnsupportedOperation, InternalServerError, SlowStreamRate

async def callback(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while not reader.at_eof():
        header_component: BaseHeaderComponent = None
        try:
            header_component: BaseHeaderComponent = await process_component(n_bytes=REQUEST_CONSTANTS.header.max_bytesize,
                                                                            reader=reader,
                                                                            component_type='header',
                                                                            timeout=SERVER_CONFIG.read_timeout)
            if not header_component:
                raise SlowStreamRate('Unable to parse header')
            handler: Callable[[BaseHeaderComponent], Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]] = TOP_LEVEL_REQUEST_MAPPING.get(header_component.category)
            if not handler:
                raise UnsupportedOperation(f'Operation category must be in: {", ".join(CategoryFlag._member_names_)}')

            response_header, response_body = await handler(header_component)
            body_stream: bytes = None
            if response_body:
                body_stream: bytes = orjson.dumps(response_body.model_dump())
                response_header.body_size = len(body_stream)
            
            await send_response(writer=writer, header=response_header, body=body_stream)
            if response_header.ended_connection or not header_component.connection_keepalive:
                writer.write_eof()
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

        except Exception as e:
            connection_end: bool = False if not header_component else header_component.finish
            response: ResponseHeader = ResponseHeader.from_protocol_exception(exc=e if isinstance(e, ProtocolException) else InternalServerError,
                                                                            version=config.version if not header_component else header_component.version,
                                                                            end_conn=connection_end,
                                                                            host=str(SERVER_CONFIG.host),
                                                                            port=SERVER_CONFIG.port)
            await send_response(writer=writer, header=response)
            if connection_end:
                writer.write_eof()
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return


async def main() -> None:
    # Initialize all extensions that the server depends on
    await init_connection_master(conninfo=make_conninfo(user=os.environ['PG_USERNAME'], password=os.environ['PG_PASSWORD'], host=os.environ['PG_HOST'], port=os.environ['PG_PORT'], dbname=os.environ['PG_DBNAME']))
    init_user_master()
    init_file_lock()
    init_caches()
    init_logger()

    # Start server
    # partial is used to pass the SERVER_CONFIG and the REQUEST_CONSTANTS model
    server: asyncio.Server = await asyncio.start_server(client_connected_cb=callback,
                                                        host=str(SERVER_CONFIG.host), port=SERVER_CONFIG.port)
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
import asyncio
import os
import sys
import orjson
from functools import partial
from typing import Optional, Any, Coroutine, Callable

from models.constants import load_constants, REQUEST_CONSTANTS, RequestConstants
from models.flags import CategoryFlag
from models.request_model import BaseHeaderComponent
from models.response_models import ResponseHeader, ResponseBody

from psycopg.conninfo import make_conninfo

from server.bootup import init_connection_master, init_user_master, init_file_lock, init_caches, init_logger
from server.comms_utils.incoming import process_component
from server.comms_utils.outgoing import send_response
from server.config.server_config import load_server_config, ServerConfig
from server.dispatch import TOP_LEVEL_REQUEST_MAPPING
from server.errors import ProtocolException, UnsupportedOperation, InternalServerError, SlowStreamRate

def prepare_callback(config: ServerConfig, request_constants: RequestConstants):
    async def callback(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while not reader.at_eof():
            header_component: BaseHeaderComponent = None
            try:
                header_component: BaseHeaderComponent = await process_component(n_bytes=request_constants.header.max_bytesize,
                                                                                reader=reader,
                                                                                component_type='header',
                                                                                timeout=config.read_timeout)
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
                
                await send_response(writer=writer, response=response_header, body=body_stream)
                
                if response_header.ended_connection or header_component.connection_keepalive:
                    writer.close()
                    await writer.wait_closed()
                    return

            except Exception as e:
                connection_end: bool = False if not header_component else header_component.finish
                response: ResponseHeader = ResponseHeader.from_protocol_exception(exc=e if isinstance(e, ProtocolException) else InternalServerError,
                                                                                version=config.version if not header_component else header_component.version,
                                                                                end_conn=connection_end,
                                                                                host=str(config.host),
                                                                                port=config.port)
                await send_response(writer=writer, response=response)
                if connection_end:
                    writer.close()
                    await writer.wait_closed()
                    return

    return callback

async def main() -> None:
    global REQUEST_CONSTANTS
    # Load global and server configurations
    if not REQUEST_CONSTANTS:
        REQUEST_CONSTANTS, _ = load_constants()
    
    config: ServerConfig = load_server_config()

    # Initialize all extensions that the server depends on
    await init_connection_master(conninfo=make_conninfo(user=os.environ['PG_USERNAME'], password=os.environ['PG_PASSWORD'], host=os.environ['PG_HOST'], port=os.environ['PG_PORT'], dbname=os.environ['PG_DBNAME']),
                                 config=config)
    init_user_master(config)
    init_file_lock(config)
    init_caches(config)
    init_logger(config)

    # Start server
    # partial is used to pass the SERVER_CONFIG and the REQUEST_CONSTANTS model
    server: asyncio.Server = await asyncio.start_server(client_connected_cb=prepare_callback(config, REQUEST_CONSTANTS),
                                                        host=str(config.host), port=config.port)
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
import asyncio
import orjson
import os
from functools import partial
from types import FunctionType
from psycopg.conninfo import make_conninfo
from server import response_codes
from server.bootup import init_connection_master, init_user_master, init_file_lock
from server.comms_utils.incoming import process_header
from server.comms_utils.outgoing import send_response
from server.config import ServerConfig, CategoryFlag
from server.dispatch import TOP_LEVEL_REQUEST_MAPPING
from server.errors import ProtocolException, UnsupportedOperation, InternalServerError, SlowStreamRate
from server.models.request_model import BaseHeaderComponent
from server.models.response_models import ResponseHeader

async def callback(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        header_component: BaseHeaderComponent = await process_header(ServerConfig.HEADER_READ_BYTESIZE.value, reader, writer)
        if not header_component:
            raise SlowStreamRate('Unable to parse header')
        
        handler: FunctionType = TOP_LEVEL_REQUEST_MAPPING.get(header_component.category)
        if not handler:
            raise UnsupportedOperation(f'Operation category must be in: {", ".join(CategoryFlag._member_names_)}')
        
        await handler(header_component)
    except Exception as e:
        connection_end: bool = False if not header_component else header_component.finish
        response: ResponseHeader = ResponseHeader.from_protocol_exception(exc=e if issubclass(e, ProtocolException) else InternalServerError,
                                                                          context_request=header_component,
                                                                          end_conn=connection_end)
        return await send_response(writer=writer, response=response, close_conn=connection_end)

async def main() -> None:
    # Check runtime dependencies
    if not response_codes:
        raise RuntimeError('No response codes found, server cannot start...')
    
    # Initialize all extensions that the server depends on
    init_user_master(ServerConfig)
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
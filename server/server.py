import asyncio
import os
import orjson
from functools import partial
from typing import Optional, Any, Coroutine, Callable
from psycopg.conninfo import make_conninfo
from server.bootup import init_connection_master, init_user_master, init_file_lock
from server.comms_utils.incoming import process_header
from server.comms_utils.outgoing import send_response
from server.config import ServerConfig, CategoryFlag
from server.dispatch import TOP_LEVEL_REQUEST_MAPPING
from server.errors import ProtocolException, UnsupportedOperation, InternalServerError, SlowStreamRate
from server.models.request_model import BaseHeaderComponent
from server.models.response_models import ResponseHeader, ResponseBody

async def callback(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while not reader.at_eof():
        try:
            header_component: BaseHeaderComponent = await process_header(ServerConfig.HEADER_READ_BYTESIZE.value, reader)
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
                                                                              context_request=header_component,
                                                                              end_conn=connection_end)
            await send_response(writer=writer, response=response)
            if connection_end:
                writer.close()
                await writer.wait_closed()
                return
            

async def main() -> None:    
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
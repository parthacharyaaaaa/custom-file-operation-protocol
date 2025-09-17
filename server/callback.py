import asyncio
from traceback import format_exc, format_exception_only
from types import MappingProxyType
from typing import Optional, TYPE_CHECKING

from models.flags import CategoryFlag
from models.request_model import BaseHeaderComponent
from models.response_models import ResponseHeader
from models.constants import REQUEST_CONSTANTS
from models.typing import ProtocolComponent

from server import errors
from server import logging
from server.comms_utils.incoming import process_component
from server.comms_utils.outgoing import send_response
from server.database import models as db_models
from server.dependencies import ServerSingletonsRegistry
from server.typing import PartialisedRequestHandler

__all__ = ('callback',)

if TYPE_CHECKING: assert REQUEST_CONSTANTS

async def callback(dependency_registry: ServerSingletonsRegistry,
                   request_handler_mapping: MappingProxyType[CategoryFlag, PartialisedRequestHandler],
                   reader: asyncio.StreamReader,
                   writer: asyncio.StreamWriter) -> None:
    while not reader.at_eof():
        header_component: Optional[ProtocolComponent] = None
        try:
            header_component = await process_component(n_bytes=REQUEST_CONSTANTS.header.max_bytesize,
                                                       reader=reader,
                                                       component_type='header',
                                                       timeout=dependency_registry.server_config.socket_connection_timeout)
            
            if not header_component:
                raise errors.SlowStreamRate('Unable to parse header')
            assert isinstance(header_component, BaseHeaderComponent)

            handler: Optional[PartialisedRequestHandler] = request_handler_mapping.get(header_component.category)
            if not handler:
                raise errors.UnsupportedOperation(f'Operation category must be in: {", ".join(CategoryFlag._member_names_)}')

            response_header, response_body = await handler(stream_reader=reader,
                                                           header_component=header_component,
                                                           server_singleton_registry=dependency_registry)
            body_stream: Optional[bytes] = None
            if response_body:
                body_stream = response_body.model_dump_json().encode('utf-8')
                response_header.body_size = len(body_stream)
            
            await send_response(writer=writer, header=response_header, body=body_stream)
            if response_header.ended_connection:
                writer.write_eof()
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

        except Exception as e:
            print(format_exc(), flush=True)
            is_caught: bool = isinstance(e, errors.ProtocolException)
            if not is_caught:
                asyncio.create_task(
                    logging.enqueue_log(waiting_period=dependency_registry.server_config.log_waiting_period,
                                        queue=dependency_registry.log_queue,
                                        log=db_models.ActivityLog(reported_severity=db_models.Severity.CRITICAL_FAILURE,
                                                                  log_category=db_models.LogType.INTERNAL,
                                                                  logged_by=db_models.LogAuthor.EXCEPTION_FALLBACK,
                                                                  log_details=format_exception_only(e)[0])))
            
            if isinstance(e, errors.SlowStreamRate) and not header_component:   # Failure to read header component past socket_connection_timeout
                writer.close()
                await writer.wait_closed()
                return
            
            assert header_component is None or isinstance(header_component, BaseHeaderComponent)
            connection_end: bool = False if not header_component else header_component.finish   # Explicit request to end connection from the client
            response: ResponseHeader = ResponseHeader.from_protocol_exception(exc=e.__class__ if is_caught else errors.InternalServerError,
                                                                              version=dependency_registry.server_config.version if not header_component else header_component.version,
                                                                              end_conn=connection_end,
                                                                              host=str(dependency_registry.server_config.host),
                                                                              port=dependency_registry.server_config.port)
                
            await send_response(writer=writer, header=response)
            if connection_end:
                writer.write_eof()
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

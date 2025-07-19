import asyncio
from typing import Optional, Any, Coroutine, Callable, Mapping
from traceback import format_exc, format_exception_only

from models.flags import CategoryFlag
from models.request_model import BaseHeaderComponent
from models.response_models import ResponseHeader, ResponseBody
from models.constants import REQUEST_CONSTANTS

from server import errors
from server import logging
from server.bootup import log_queue
from server.comms_utils.incoming import process_component
from server.comms_utils.outgoing import send_response
from server.config.server_config import ServerConfig
from server.database import models as db_models
from server.dispatch import TOP_LEVEL_REQUEST_MAPPING

async def callback(dependencies_mapping: Mapping[type, Any], reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while not reader.at_eof():
        header_component: BaseHeaderComponent = None
        try:
            header_component: BaseHeaderComponent = await process_component(n_bytes=REQUEST_CONSTANTS.header.max_bytesize,
                                                                            reader=reader,
                                                                            component_type='header',
                                                                            timeout=dependencies_mapping[ServerConfig].read_timeout)
            if not header_component:
                raise errors.SlowStreamRate('Unable to parse header')
            handler: Callable[[asyncio.StreamReader, BaseHeaderComponent], Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]] = TOP_LEVEL_REQUEST_MAPPING.get(header_component.category)
            if not handler:
                raise errors.UnsupportedOperation(f'Operation category must be in: {", ".join(CategoryFlag._member_names_)}')

            response_header, response_body = await handler(reader, header_component)
            body_stream: bytes = None
            if response_body:
                body_stream: bytes = response_body.model_dump_json().encode('utf-8')
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
            connection_end: bool = False if not header_component else header_component.finish
            is_caught: bool = isinstance(e, errors.ProtocolException)
            response: ResponseHeader = ResponseHeader.from_protocol_exception(exc=e if is_caught else errors.InternalServerError,
                                                                              version=config.version if not header_component else header_component.version,
                                                                              end_conn=connection_end,
                                                                              host=str(dependencies_mapping[ServerConfig].read_timeout),
                                                                              port=dependencies_mapping[ServerConfig].read_timeout)
            # Log uncaught exceptions
            if not is_caught:
                asyncio.create_task(
                    logging.enqueue_log(waiting_period=dependencies_mapping[ServerConfig].read_timeout.log_waiting_period, queue=log_queue,
                                        log=db_models.ActivityLog(severity=db_models.Severity.CRITICAL_FAILURE.value,
                                                                  log_category=db_models.LogType.INTERNAL.value,
                                                                  logged_by=db_models.LogAuthor.EXCEPTION_FALLBACK.value,
                                                                  log_details=format_exception_only(e)[0])))
                
            await send_response(writer=writer, header=response)
            if connection_end:
                writer.write_eof()
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

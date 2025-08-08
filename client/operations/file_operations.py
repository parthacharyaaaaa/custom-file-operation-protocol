import asyncio
import aiofiles
import os
import math
from typing import Optional, Union, Any, Sequence

from client.cmd.cmd_utils import display
from client.cmd.message_strings import file_messages, general_messages
from client.communication.outgoing import send_request
from client.communication.incoming import process_response
from client.operations import utils as op_utils
from client.communication import utils as comms_utils
from client.config import constants as client_constants
from client import session_manager

from models.constants import REQUEST_CONSTANTS
from models.cursor_flag import CursorFlag
from models.flags import CategoryFlag, FileFlags
from models.response_codes import SuccessFlags, IntermediaryFlags
from models.request_model import BaseHeaderComponent, BaseFileComponent, BaseAuthComponent

async def send_amendment_chunks(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                                header_component: BaseHeaderComponent,
                                auth_component: BaseAuthComponent,
                                file_component: BaseFileComponent,
                                write_view: memoryview,
                                client_config: client_constants.ClientConfig,
                                post_op_cursor_keepalive: bool = False, end_connection: bool = False):
    for offset in range(0, len(write_view), file_component.chunk_size):
        file_component.write_data = write_view[offset:offset+file_component.chunk_size]
        end_reached = offset + file_component.chunk_size >= len(write_view)
        if end_reached:
            file_component.end_operation = True
            file_component.cursor_bitfield |= CursorFlag.POST_OPERATION_CURSOR_KEEPALIVE if post_op_cursor_keepalive else 0
            header_component.finish = end_connection

        await send_request(writer=writer,
                            header_component=header_component,
                            auth_component=auth_component,
                            body_component=file_component)

        response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
        if response_header.code != SuccessFlags.SUCCESSFUL_AMEND.value:
            return False
    return True

async def replace_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                              write_data: Union[str, bytes, bytearray],
                              file_component: BaseFileComponent,
                              client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                              post_op_cursor_keepalive: bool = False, end_connection: bool = False) -> None:
    '''Completely replace the contents of an existing remote file'''
    write_view: memoryview = op_utils.cast_as_memoryview(write_data)
    view_length = len(write_view)

    file_component.chunk_size = min(REQUEST_CONSTANTS.file.max_bytesize, min(view_length, file_component.chunk_size or REQUEST_CONSTANTS.file.chunk_max_size))
    file_component.write_data = write_view[:file_component.chunk_size]
    file_component.end_operation = len(file_component.write_data) == view_length
    if file_component.end_operation and post_op_cursor_keepalive:
        file_component.cursor_bitfield |= CursorFlag.POST_OPERATION_CURSOR_KEEPALIVE

    # Initial header component would be file overwrite to truncate the previous file
    header_component: BaseHeaderComponent = comms_utils.make_header_component(client_config, session_manager, CategoryFlag.FILE_OP, FileFlags.OVERWRITE)
    await send_request(writer=writer,
                       header_component=header_component,
                       auth_component=session_manager.auth_component,
                       body_component=file_component)
    
    response_header, response_body = await process_response(reader=reader, writer=writer, timeout=client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_AMEND.value:
        await display(file_messages.failed_file_operation(file_component.subject_file_owner, file_component.subject_file, FileFlags.OVERWRITE, response_header.code))
        return
    
    if not file_component.end_operation:
        header_component.subcategory = FileFlags.APPEND
        file_component.cursor_bitfield &= CursorFlag.POST_OPERATION_CURSOR_KEEPALIVE
        success: bool = await send_amendment_chunks(reader=reader, writer=writer,
                                                    header_component=header_component,
                                                    file_component=file_component,
                                                    auth_component=session_manager.auth_component,
                                                    write_view=write_view[file_component.chunk_size:],
                                                    client_config=client_config,
                                                    post_op_cursor_keepalive=post_op_cursor_keepalive,
                                                    end_connection=end_connection)
        if not success:
            await display(file_messages.failed_file_operation(file_component.subject_file_owner, file_component.subject_file, FileFlags.APPEND, response_header.code))
            return
    
    await display(file_messages.successful_file_amendment(file_component.subject_file_owner, file_component.subject_file, SuccessFlags.SUCCESSFUL_AMEND.value))

async def write_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                            write_data: Union[str, bytes, bytearray, memoryview],
                            file_component: BaseFileComponent,
                            client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager) -> None:
    if isinstance(write_data, str):
        write_data = write_data.encode('utf-8')
    
    write_view: memoryview = write_data if isinstance(write_data, memoryview) else memoryview(write_data)
    view_length = len(write_view)

    file_component.chunk_size = min(REQUEST_CONSTANTS.file.max_bytesize, min(view_length, file_component.chunk_size or REQUEST_CONSTANTS.file.chunk_max_size))
    valid_responses: tuple[str] = (SuccessFlags.SUCCESSFUL_AMEND.value, IntermediaryFlags.PARTIAL_AMEND.value)

    header_component: BaseHeaderComponent = comms_utils.make_header_component(client_config, session_manager, CategoryFlag.FILE_OP, FileFlags.WRITE)
    for offset in range(0, view_length, file_component.chunk_size):
        end_reached: bool = offset + file_component.chunk_size >= view_length
        file_component.write_data = write_view[offset:offset+file_component.chunk_size]
        file_component.cursor_bitfield

        await send_request(writer=writer,
                           header_component=header_component,
                           auth_component=session_manager.auth_component,
                           body_component=file_component)

        header_component.subcategory = FileFlags.APPEND
        response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
        if response_header.code not in valid_responses:
            await display(file_messages.failed_file_operation(file_component.subject_file_owner, file_component.subject_file, FileFlags.APPEND, response_header.code))
            return
        file_component.cursor_position += len(file_component.write_data)
    
    await display(file_messages.successful_file_amendment(file_component.subject_file_owner, file_component.subject_file, SuccessFlags.SUCCESSFUL_AMEND.value))

async def append_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                             write_data: Union[str, bytes, bytearray, memoryview],
                             file_component: BaseFileComponent, chunk_size: int,
                             client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                             end_connection: bool = False) -> None:
    if isinstance(write_data, str):
        write_data = write_data.encode('utf-8')
    write_view: memoryview = write_data if isinstance(write_data, memoryview) else memoryview(write_data)
    view_length = len(write_view)

    header_component: BaseHeaderComponent = comms_utils.make_header_component(client_config, session_manager, CategoryFlag.FILE_OP, FileFlags.APPEND)
    chunk_size = min(REQUEST_CONSTANTS.file.chunk_max_size, chunk_size)

    for offset in range(0, view_length, chunk_size):
        file_component.write_data = write_view[offset:offset+chunk_size]
        file_component.chunk_size = len(file_component.write_data)
        print(bytes(file_component.write_data))

        end_reached: bool = (offset + file_component.chunk_size) >= view_length
        file_component.cursor_keepalive = not end_reached
        header_component.finish = end_connection and end_reached

        await send_request(writer=writer,
                           header_component=header_component,
                           auth_component=session_manager.auth_component,
                           body_component=file_component)

        response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
        if response_header.code != SuccessFlags.SUCCESSFUL_AMEND.value:
            await display(file_messages.failed_file_operation(file_component.subject_file_owner, file_component.subject_file, FileFlags.APPEND, response_header.code))
            return
    
    await display(file_messages.successful_file_amendment(file_component.subject_file_owner, file_component.subject_file, SuccessFlags.SUCCESSFUL_AMEND.value))

async def read_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                           file_component: BaseFileComponent,
                           client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                           read_limit: Optional[int] = None, chunked_display: bool = True) -> bytearray:
    read_data: bytearray = bytearray()
    bytes_read: int = 0
    
    header_component: BaseHeaderComponent = comms_utils.make_header_component(client_config, session_manager, CategoryFlag.FILE_OP, FileFlags.READ)

    if not read_limit:
        read_limit = math.inf
    while bytes_read < read_limit:
        file_component.cursor_keepalive = (read_limit - len(read_data)) < REQUEST_CONSTANTS.file.chunk_max_size
        file_component.chunk_size = min(read_limit-bytes_read, file_component.chunk_size)
        
        await send_request(writer,
                           header_component=header_component,
                           auth_component=session_manager.auth_component,
                           body_component=file_component)
        response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
        # TODO: Add notice/suspension for ongoing amendments

        if response_header.code != SuccessFlags.SUCCESSFUL_READ.value:
            await display(file_messages.failed_file_operation(file_component.subject_file_owner, file_component.subject_file, FileFlags.READ, code=response_header.code))
            return
        
        remote_read_data: bytes = response_body.contents.get('read')
        if remote_read_data is None:
            await display(general_messages.missing_response_claim('read'))
            return
        
        file_component.cursor_position += len(remote_read_data)
        file_component.cursor_cached = True
        bytes_read += len(remote_read_data)

        if chunked_display:
            await display(remote_read_data)
        else:
            read_data.append(remote_read_data)
        
        if response_body.operation_ended:
            break
    
    if not chunked_display:
        await display(read_data)

async def create_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                      file_component: BaseFileComponent,
                      client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                      end_connection: bool = False) -> dict[str, Any]:
    header_component: BaseHeaderComponent = comms_utils.make_header_component(client_config, session_manager, CategoryFlag.FILE_OP, FileFlags.CREATE, finish=end_connection)
    await send_request(writer,
                       header_component=header_component,
                       auth_component=session_manager.auth_component,
                       body_component=file_component)
    
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_FILE_CREATION.value:
        await display(file_messages.failed_file_operation(file_component.subject_file_owner, file_component.subject_file, FileFlags.CREATE, response_header.code))
        return
    
    iso_epoch, = await comms_utils.filter_claims(response_body.contents, "iso_epoch", default="N\A")

    await display(file_messages.succesful_file_creation(file_component.subject_file_owner, file_component.subject_file, iso_epoch, response_header.code))

async def delete_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                      file_component: BaseFileComponent,
                      client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager) -> None:
    header_component: BaseHeaderComponent = comms_utils.make_header_component(client_config, session_manager, CategoryFlag.FILE_OP, FileFlags.DELETE)
    await send_request(writer,
                       header_component=header_component,
                       auth_component=session_manager.auth_component,
                       body_component=file_component)
    
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_FILE_DELETION:
        await display(file_messages.failed_file_operation(file_component.subject_file_owner, file_component.subject_file, FileFlags.DELETE, response_header.code))

    revoked_info: list[dict[str, str]] = response_body.contents.get('revoked_grantee_info', [])
    if revoked_info == []:
        await display(general_messages.malformed_response_body('revoked_grantee_info'))
    
    # No need to check inner types, anything over a byte stream can be used in f-strings anyways.
    # Although hinted as a list, any Sequence subclass passes as we only need to iterate over it
    elif not (isinstance(revoked_info, Sequence) and all(isinstance(i, dict) for i in revoked_info)):
        await display(general_messages.malformed_response_body("Mismatched data types in response body sent by server"))
        return
    
    deletion_iso_datetime: str = response_body.contents.get('deletion_time')
    if not deletion_iso_datetime:
        await display(general_messages.malformed_response_body('deletion_time'))

    deletion_iso_datetime, = await comms_utils.filter_claims(response_body.contents, "deletion_time")

    await display(file_messages.succesful_file_deletion(file_component.subject_file_owner, file_component.subject_file, revoked_info, deletion_iso_datetime, response_header.code))

async def upload_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                             local_fpath: str, 
                             client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                             remote_filename: Optional[str] = None, chunk_size: Optional[int] = None,
                             end_connection: bool = False, cursor_keepalive: bool = False) -> None:
    if not os.path.isfile(local_fpath):
        await display(file_messages.file_not_found(local_fpath))
    
    if not remote_filename:
        remote_filename = os.path.basename(local_fpath)

    # Create remote file
    file_creation_component: BaseFileComponent = BaseFileComponent(subject_file=remote_filename, subject_file_owner=session_manager.identity, cursor_keepalive=cursor_keepalive)
    await send_request(writer,
                       BaseHeaderComponent(version=client_config.version, finish=end_connection, category=CategoryFlag.FILE_OP, subcategory=FileFlags.CREATE),
                       session_manager.auth_component,
                       file_creation_component)

    creation_response_header, creation_response_body = await process_response(reader, writer, client_config.read_timeout)
    if creation_response_header != SuccessFlags.SUCCESSFUL_FILE_CREATION:
        await display(file_messages.failed_file_operation(session_manager.identity, remote_filename, FileFlags.CREATE, response_header.code))
        return
    
    iso_epoch, = await comms_utils.filter_claims(response_body.contents, "iso_epoch")

    await display(file_messages.succesful_file_creation(session_manager.identity, remote_filename, iso_epoch or 'N\A'))

    chunk_size = max(REQUEST_CONSTANTS.file.max_bytesize, (chunk_size or -1))
    valid_responses: tuple[str] = (SuccessFlags.SUCCESSFUL_AMEND.value, IntermediaryFlags.PARTIAL_AMEND.value)
    async with aiofiles.open(local_fpath, 'rb') as src_file:
        while contents := await src_file.read(chunk_size):
            eof_reached: bool = len(contents) < chunk_size
            file_component: BaseFileComponent = BaseFileComponent(subject_file=remote_filename, subject_file_owner=session_manager.identity,
                                                                  chunk_size=chunk_size, write_data=contents,
                                                                  cursor_keepalive=eof_reached)

            await send_request(writer, BaseHeaderComponent(client_config.version, finish=eof_reached, category=CategoryFlag.FILE_OP, subcategory=FileFlags.APPEND), session_manager.auth_component, file_component)

            response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
            if response_header.code not in valid_responses:
                await display(file_messages.successful_file_amendment(session_manager.identity, remote_filename, response_header.code))
                return
    
    await display(file_messages.successful_file_amendment(session_manager.identity, remote_filename))

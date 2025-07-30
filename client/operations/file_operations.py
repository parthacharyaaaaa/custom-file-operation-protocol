import asyncio
import aiofiles
import os
import math
from typing import Optional, Union, Any, Sequence

from client.cmd.cmd_utils import display
from client.cmd.message_strings import file_messages, general_messages
from client.communication.outgoing import send_request
from client.communication.incoming import process_response
from client.communication import utils as comms_utils
from client.config import constants as client_constants
from client import session_manager

from models.constants import REQUEST_CONSTANTS
from models.flags import CategoryFlag, FileFlags
from models.response_codes import SuccessFlags, IntermediaryFlags
from models.request_model import BaseHeaderComponent, BaseFileComponent

async def append_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                             write_data: Union[str, bytes, bytearray, memoryview],
                             remote_directory: str, remote_filename,
                             client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                             chunk_size: Optional[int] = None) -> None:
    if isinstance(write_data, str):
        write_data = write_data.encode('utf-8')
    
    write_view: memoryview = write_data if isinstance(write_data, memoryview) else memoryview(write_data)
    view_length = len(write_view)

    chunk_size = min(REQUEST_CONSTANTS.file.max_bytesize, min(view_length, chunk_size or REQUEST_CONSTANTS.file.chunk_max_size))
    valid_responses: tuple[str] = (SuccessFlags.SUCCESSFUL_AMEND.value, IntermediaryFlags.PARTIAL_AMEND.value)

    for offset in range(0, view_length, chunk_size):
        chunk: memoryview = write_view[offset:offset+chunk_size]
        end_reached: bool = offset + chunk_size >= view_length
        file_component: BaseFileComponent = BaseFileComponent(subject_file=remote_filename, subject_file_owner=remote_directory,
                                                                chunk_size=chunk_size, write_data=chunk,
                                                                return_partial=True, cursor_keepalive=end_reached)

        await send_request(writer, BaseHeaderComponent(client_config.version, finish=end_reached, category=CategoryFlag.FILE_OP, subcategory=FileFlags.APPEND), session_manager.auth_component, file_component)

        response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
        if response_header.code not in valid_responses:
            await display(file_messages.failed_file_operation(remote_directory, remote_filename, FileFlags.APPEND, response_header.code))
            return
    
    await display(file_messages.successful_file_amendment(remote_directory, remote_filename, SuccessFlags.SUCCESSFUL_AMEND.value))

async def read_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                           remote_directory: str, remote_filename: str,
                           client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                           chunk_size: Optional[int] = None, read_limit: Optional[int] = None, chunked_display: bool = True) -> bytearray:
    read_data: bytearray = bytearray()

    if not chunk_size:
        chunk_size = REQUEST_CONSTANTS.file.chunk_max_size
    else:
        chunk_size = min(REQUEST_CONSTANTS.file.chunk_max_size, abs(chunk_size))
    
    remote_cursor_position: int = 0
    valid_responses: tuple[str, str] = (IntermediaryFlags.PARTIAL_READ.value, SuccessFlags.SUCCESSFUL_READ.value)

    if not read_limit:
        read_limit = math.inf
    while len(read_data) < read_limit:
        file_component: BaseFileComponent = BaseFileComponent(subject_file=remote_filename, subject_file_owner=remote_directory,
                                                              chunk_size=chunk_size, cursor_position=remote_cursor_position,
                                                              cursor_keepalive=True)
        await send_request(writer, header_component=BaseHeaderComponent(client_config.version, category=CategoryFlag.FILE_OP, subcategory=FileFlags.READ),
                           auth_component=session_manager.auth_component,
                           body_component=file_component)
        response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
        # TODO: Add notice/suspension for ongoing amendments

        if response_header.code not in valid_responses:
            await display(file_messages.failed_file_operation(remote_directory, remote_filename, FileFlags.READ, code=response_header.code))
            return
        
        read_finished: bool = response_header.code == SuccessFlags.SUCCESSFUL_READ.value
        remote_read_data: bytes = response_body.get('read')

        if remote_read_data is None and not read_finished:
            await display(general_messages.missing_response_claim('read'))

        if not chunked_display:
            read_data.append(remote_read_data)
        else:
            await display(remote_read_data)

        if read_finished:
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

    iso_epoch: str = response_body.contents.get('iso_epoch')
    if not iso_epoch:
        await display(general_messages.missing_response_claim('iso_epoch'))

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
    
    iso_epoch: str = creation_response_body.contents.get('iso_epoch')
    if not iso_epoch:
        await display(general_messages.missing_response_claim('iso_epoch'))

    await display(file_messages.succesful_file_creation(session_manager.identity, remote_filename, iso_epoch or 'N\A'))

    chunk_size = max(REQUEST_CONSTANTS.file.max_bytesize, (chunk_size or -1))
    valid_responses: tuple[str] = (SuccessFlags.SUCCESSFUL_AMEND.value, IntermediaryFlags.PARTIAL_AMEND.value)
    async with aiofiles.open(local_fpath, 'rb') as src_file:
        while contents := await src_file.read(chunk_size):
            eof_reached: bool = len(contents) < chunk_size
            file_component: BaseFileComponent = BaseFileComponent(subject_file=remote_filename, subject_file_owner=session_manager.identity,
                                                                  chunk_size=chunk_size, write_data=contents,
                                                                  return_partial=True, cursor_keepalive=eof_reached)

            await send_request(writer, BaseHeaderComponent(client_config.version, finish=eof_reached, category=CategoryFlag.FILE_OP, subcategory=FileFlags.APPEND), session_manager.auth_component, file_component)

            response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
            if response_header.code not in valid_responses:
                await display(file_messages.successful_file_amendment(session_manager.identity, remote_filename, response_header.code))
                return
    
    await display(file_messages.successful_file_amendment(session_manager.identity, remote_filename))

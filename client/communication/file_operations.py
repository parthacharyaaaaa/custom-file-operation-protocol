import asyncio
import aiofiles
import os
import math
from typing import Optional, Union, Any

from client.bootup import session_manager
from client.config.constants import CLIENT_CONFIG
from client.communication.outgoing import send_request
from client.communication.incoming import process_response

from models.constants import REQUEST_CONSTANTS
from models.flags import CategoryFlag, FileFlags
from models.response_codes import SuccessFlags, IntermediaryFlags
from models.request_model import BaseHeaderComponent, BaseFileComponent

async def upload_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, fpath: str, remote_directory: str, remote_filename: Optional[str] = None, chunk_size: Optional[int] = None) -> None:
    if not os.path.isfile(fpath):
        raise FileNotFoundError(f'File {fpath} not found')
    
    if not remote_filename:
        remote_filename = os.path.basename(fpath)
    
    chunk_size = max(REQUEST_CONSTANTS.file.max_bytesize, (chunk_size or -1))
    chunk_number: int = 0
    valid_responses: tuple[str] = (SuccessFlags.SUCCESSFUL_AMEND.value, IntermediaryFlags.PARTIAL_AMEND.value)
    async with aiofiles.open(fpath, 'rb') as src_file:
        while contents := await src_file.read(chunk_size):
            eof_reached: bool = len(contents) < chunk_size
            file_component: BaseFileComponent = BaseFileComponent(subject_file=remote_filename, subject_file_owner=remote_directory,
                                                                  chunk_size=chunk_size, chunk_number=chunk_number, write_data=contents,
                                                                  return_partial=True, cursor_keepalive=eof_reached)

            await send_request(writer, BaseHeaderComponent(CLIENT_CONFIG.version, finish=eof_reached, category=CategoryFlag.FILE_OP, subcategory=FileFlags.APPEND), session_manager.auth_component, file_component)

            response_header, response_body = await process_response(reader, writer, CLIENT_CONFIG.read_timeout)
            if response_header.code not in valid_responses:
                raise Exception
            
            chunk_number+=1

async def append_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, write_data: Union[str, bytes, bytearray, memoryview], remote_directory: str, remote_filename, chunk_size: Optional[int] = None) -> None:
    if isinstance(write_data, str):
        write_data = write_data.encode('utf-8')
    
    write_view: memoryview = write_data if isinstance(write_data, memoryview) else memoryview(write_data)
    view_length = len(write_view)

    chunk_size = min(REQUEST_CONSTANTS.file.max_bytesize, min(view_length, chunk_size or REQUEST_CONSTANTS.file.chunk_max_size))
    valid_responses: tuple[str] = (SuccessFlags.SUCCESSFUL_AMEND.value, IntermediaryFlags.PARTIAL_AMEND.value)

    for chunk_number, offset in enumerate(range(0, view_length, chunk_size)):
        chunk: memoryview = write_view[offset:offset+chunk_size]
        end_reached: bool = offset + chunk_size >= view_length
        file_component: BaseFileComponent = BaseFileComponent(subject_file=remote_filename, subject_file_owner=remote_directory,
                                                                chunk_size=chunk_size, chunk_number=chunk_number, write_data=chunk,
                                                                return_partial=True, cursor_keepalive=end_reached)

        await send_request(writer, BaseHeaderComponent(CLIENT_CONFIG.version, finish=end_reached, category=CategoryFlag.FILE_OP, subcategory=FileFlags.APPEND), session_manager.auth_component, file_component)

        response_header, response_body = await process_response(reader, writer, CLIENT_CONFIG.read_timeout)
        if response_header.code not in valid_responses:
            raise Exception
        

async def read_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, remote_directory: str, remote_filename: str, chunk_size: Optional[int] = None, read_limit: Optional[int] = None) -> bytearray:
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
        await send_request(writer, header_component=BaseHeaderComponent(CLIENT_CONFIG.version, category=CategoryFlag.FILE_OP, subcategory=FileFlags.READ),
                           auth_component=session_manager.auth_component,
                           body_component=file_component)
        response_header, response_body = await process_response(reader, writer, CLIENT_CONFIG.read_timeout)

        if response_header.code not in valid_responses:
            raise Exception
        
        read_data.append(response_body.contents['read'])
        # TODO: Add notice/suspension for ongoing amendments

        if response_header.code == SuccessFlags.SUCCESSFUL_READ.value:  # File read complete
            break
    return read_data

async def create_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, remote_directory: str, remote_filename: str) -> dict[str, Any]:
    file_component: BaseFileComponent = BaseFileComponent(subject_file=remote_filename, subject_file_owner=remote_directory)

    await send_request(writer, header_component=BaseHeaderComponent(CLIENT_CONFIG.version, category=CategoryFlag.FILE_OP, subcategory=FileFlags.CREATE),
                    auth_component=session_manager.auth_component,
                    body_component=file_component)
    
    response_header, response_body = await process_response(reader, writer, CLIENT_CONFIG.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_FILE_CREATION:
        raise Exception
    
    return response_body['contents']

async def delete_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, remote_directory: str, remote_filename: str) -> None:
    file_component: BaseFileComponent = BaseFileComponent(subject_file=remote_filename, subject_file_owner=remote_directory)

    await send_request(writer, header_component=BaseHeaderComponent(CLIENT_CONFIG.version, category=CategoryFlag.FILE_OP, subcategory=FileFlags.DELETE),
                    auth_component=session_manager.auth_component,
                    body_component=file_component)
    
    response_header, _ = await process_response(reader, writer, CLIENT_CONFIG.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_FILE_DELETION:
        raise Exception
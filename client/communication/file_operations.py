import asyncio
import aiofiles
import os
from typing import Optional

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
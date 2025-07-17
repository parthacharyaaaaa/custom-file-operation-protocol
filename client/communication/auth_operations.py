import asyncio

from client.communication.outgoing import send_request
from client.communication.incoming import process_response
from client.config.constants import CLIENT_CONFIG
from client.cmd.cmd_utils import display
from client.cmd.message_strings import auth_messages
from client.cmd.message_strings import general_messages

from pydantic import ValidationError

from models.request_model import BaseHeaderComponent, BaseAuthComponent
from models.flags import CategoryFlag, AuthFlags
from models.response_codes import SuccessFlags

async def create_remote_user(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, username: str, password: str) -> None:
    try:
        auth_component: BaseAuthComponent = BaseAuthComponent(identity=username, password=password)
    except ValidationError as v:
        await display(auth_messages.invalid_user_data(v), sep=b' : ')
        return
    
    await send_request(writer=writer,
                       header_component=BaseHeaderComponent(version=CLIENT_CONFIG.version, category=CategoryFlag.AUTH, subcategory=AuthFlags.REGISTER),
                       auth_component=auth_component)
    response_header, _ = await process_response(reader, writer, CLIENT_CONFIG.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_USER_CREATION.value:
        await display(auth_messages.failed_auth_operation(operation=AuthFlags.REGISTER, code=response_header.code))
        return
    
    await display()

async def delete_remote_user(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, username: str, password: str) -> None:
    try:
        auth_component: BaseAuthComponent = BaseAuthComponent(identity=username, password=password)
    except ValidationError as v:
        await display(auth_messages.invalid_user_data(v))
        return
    
    await send_request(writer,
                       header_component=BaseHeaderComponent(version=CLIENT_CONFIG.version, category=CategoryFlag.AUTH, subcategory=AuthFlags.DELETE),
                       auth_component=auth_component)
    
    response_header, response_body = await process_response(reader, writer, CLIENT_CONFIG.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_USER_DELETION:
        await display(auth_messages.failed_auth_operation(AuthFlags.DELETE, response_header.code))
        return

    deleted_count: int = response_body.contents.get('deleted_count')
    if not deleted_count:
        await display(general_messages.missing_response_claim('deleted_count'))
    deleted_files: list[str] = response_body.contents.get('deleted_files')
    if not deleted_files:
        await display(general_messages.missing_response_claim('deleted_files'))
    if actual_fcount:=len(deleted_files) != deleted_count:
        await display(general_messages.malformed_response_body(message=auth_messages.filecount_mismatch(deleted_count, actual_fcount)))

    await display(auth_messages.successful_user_deletion(username, deleted_count, deleted_files))

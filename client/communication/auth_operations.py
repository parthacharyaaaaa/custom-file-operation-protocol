import asyncio
from typing import Any

from client.bootup import session_manager
from client.communication.outgoing import send_request
from client.communication.incoming import process_response
from client.config.constants import CLIENT_CONFIG
from client.cmd.cmd_utils import display, format_dict
from client.cmd.message_strings import auth_messages
from client.cmd.message_strings import general_messages

from pydantic import ValidationError

from models.request_model import BaseHeaderComponent, BaseAuthComponent
from models.flags import CategoryFlag, AuthFlags
from models.response_codes import SuccessFlags, ServerErrorFlags
from models.session_metadata import SessionMetadata

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


async def authorize(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, username: str, password: str, display_credentials: bool = False) -> None:
    try:
        auth_component: BaseAuthComponent = BaseAuthComponent(identity=username, password=password)
    except ValidationError as v:
        await display(auth_messages.invalid_user_data(v))
        return
    
    await send_request(writer=writer,
                       header_component=BaseHeaderComponent(version=CLIENT_CONFIG.version, category=CategoryFlag.AUTH, subcategory=AuthFlags.LOGIN),
                       auth_component=auth_component)
    
    response_header, response_body = await process_response(reader, writer, CLIENT_CONFIG.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_AUTHENTICATION:
        await display(auth_messages.failed_auth_operation(AuthFlags.LOGIN, response_header.code))
        return
    
    session_dict: dict[str, Any] = response_body.contents.get('session')
    if not session_dict:
        await display(auth_messages.failed_auth_operation(AuthFlags.LOGIN, response_header.code), general_messages.missing_response_claim('session'), sep=b'\n')
        return

    if not SessionMetadata.check_authentication_response_validity(session_dict=session_dict, validate_timestamp=True):
        await display(auth_messages.failed_auth_operation(AuthFlags.LOGIN, response_header.code), general_messages.malformed_response_body(), sep=b'\n')
        return

    session_manager.create_authentication_component(**session_dict)
    await display(auth_messages.successful_authorization(remote_user=username))
    if display_credentials:
        await display(format_dict(session_manager.session_metadata.json_repr))
    

async def reauthorize(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, display_credentials: bool = False) -> None:
    await send_request(writer, BaseHeaderComponent(version=CLIENT_CONFIG.version, category=CategoryFlag.AUTH, subcategory=AuthFlags.REFRESH))
    response_header, response_body = await process_response(reader, writer, CLIENT_CONFIG.read_timeout)

    if response_header.code != SuccessFlags.SUCCESSFUL_SESSION_REFRESH:
        await display(auth_messages.failed_auth_operation(AuthFlags.REFRESH, response_header.code))
        return
    
    new_digest: bytes = response_body.contents.get('digest')
    iteration: int = response_body.contents.get('iteration')

    if not new_digest:
        await display(auth_messages.failed_auth_operation(AuthFlags.REFRESH, ServerErrorFlags.INTERNAL_SERVER_ERROR.value),
                      general_messages.missing_response_claim('digest'),
                      sep=b'\n')
        return
    
    if not iteration:
        await display(general_messages.missing_response_claim('iteration'))

    session_manager.session_metadata.update_digest(new_digest=new_digest)

    if iteration != session_manager.session_metadata.iteration + 1:
        await display(auth_messages.session_iteration_mismatch(session_manager.session_metadata.iteration, iteration))
        session_manager.session_metadata._iteration = iteration

    await display(auth_messages.successful_reauthorization(remote_user=session_manager.identity, iteration=iteration),
                  format_dict(session_manager.session_metadata.dict_repr) if display_credentials else b'',
                  sep=b'\n')
    
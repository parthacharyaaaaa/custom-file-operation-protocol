'''Methods corresponding to client auth'''

import asyncio
from typing import Any

from client import session_manager
from client.auxillary import operational_utils
from client.config import constants as client_constants
from client.communication.outgoing import send_request
from client.communication.incoming import process_response
from client.cmd.cmd_utils import display, format_dict
from client.cmd.message_strings import auth_messages
from client.cmd.message_strings import general_messages

from pydantic import ValidationError

from models.request_model import BaseHeaderComponent, BaseAuthComponent
from models.flags import CategoryFlag, AuthFlags
from models.response_codes import SuccessFlags, ServerErrorFlags
from models.session_metadata import SessionMetadata

__all__ = ('create_remote_user',
           'delete_remote_user',
           'authorize',
           'reauthorize',
           'end_remote_session',
           'change_password')

async def create_remote_user(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                             auth_component: BaseAuthComponent,
                             client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                             display_credentials: bool = False, end_connection: bool = False) -> None:
    header_component: BaseHeaderComponent = operational_utils.make_header_component(client_config, session_manager, CategoryFlag.AUTH, AuthFlags.REGISTER, finish=end_connection)
    await send_request(writer=writer,
                       header_component=header_component,
                       auth_component=auth_component)
    
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_USER_CREATION.value:
        await display(auth_messages.failed_auth_operation(operation=AuthFlags.REGISTER, code=response_header.code))
        return
    
    epoch, username = await operational_utils.filter_claims(response_body.contents, "epoch", "username")
    await display(auth_messages.successful_user_creation(username or auth_component.identity, epoch))

async def delete_remote_user(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                             auth_component: BaseAuthComponent,
                             client_config: client_constants.ClientConfig, session_master: session_manager.SessionManager,
                             end_connection: bool = False) -> None:
    header_component: BaseHeaderComponent = operational_utils.make_header_component(client_config, session_master, CategoryFlag.AUTH, AuthFlags.DELETE, finish=end_connection)
    await send_request(writer,
                       header_component=header_component,
                       auth_component=auth_component)
    
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_USER_DELETION.value:
        await display(auth_messages.failed_auth_operation(AuthFlags.DELETE, response_header.code))
        return

    deleted_count, deleted_files = await operational_utils.filter_claims(response_body.contents, "deleted_count", "deleted_files")
    if actual_fcount:=len(deleted_files) != deleted_count:
        await display(general_messages.malformed_response_body(message=auth_messages.filecount_mismatch(deleted_count, actual_fcount)))

    await display(auth_messages.successful_user_deletion(auth_component.identity, deleted_count, deleted_files))

async def authorize(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                    auth_component: BaseAuthComponent,
                    client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                    display_credentials: bool = False, end_connection: bool = False) -> None:
    header_component: BaseHeaderComponent = operational_utils.make_header_component(client_config,  session_manager, CategoryFlag.AUTH, AuthFlags.LOGIN)
    await send_request(writer=writer,
                       header_component=header_component,
                       auth_component=auth_component)
    
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_AUTHENTICATION.value:
        await display(auth_messages.failed_auth_operation(AuthFlags.LOGIN, response_header.code))
        return
    
    session_dict: dict[str, Any] = response_body.contents.get('session')
    if not session_dict:
        await display(auth_messages.failed_auth_operation(AuthFlags.LOGIN, response_header.code), general_messages.missing_response_claim('session'), sep=b'\n')
        return

    if not SessionMetadata.check_authentication_response_validity(session_dict=session_dict, validate_timestamp=True):
        await display(auth_messages.failed_auth_operation(AuthFlags.LOGIN, response_header.code), general_messages.malformed_response_body(), sep=b'\n')
        return

    session_manager.local_authenticate(identity=auth_component.identity, **session_dict)
    await display(auth_messages.successful_authorization(remote_user=auth_component.identity))
    if display_credentials:
        await display(format_dict(session_manager.session_metadata.json_repr))
    
async def reauthorize(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                      client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                      display_credentials: bool = False) -> None:
    await send_request(writer, BaseHeaderComponent(version=client_config.version, category=CategoryFlag.AUTH, subcategory=AuthFlags.REFRESH))
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)

    if response_header.code != SuccessFlags.SUCCESSFUL_SESSION_REFRESH:
        await display(auth_messages.failed_auth_operation(AuthFlags.REFRESH, response_header.code))
        return
    
    new_digest, iteration = await operational_utils.filter_claims(response_body.contents, "digest", "iteration")
    if not new_digest:
        await display(auth_messages.failed_auth_operation(AuthFlags.REFRESH, ServerErrorFlags.INTERNAL_SERVER_ERROR.value))
        return
    
    session_manager.session_metadata.update_digest(new_digest=new_digest)

    if iteration != session_manager.session_metadata.iteration + 1:
        await display(auth_messages.session_iteration_mismatch(session_manager.session_metadata.iteration, iteration))
        session_manager.session_metadata._iteration = iteration

    await display(auth_messages.successful_reauthorization(remote_user=session_manager.identity, iteration=iteration),
                  format_dict(session_manager.session_metadata.dict_repr) if display_credentials else b'',
                  sep=b'\n')

async def end_remote_session(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                             client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                             display_credentials: bool = False, end_connection: bool = False) -> None:
    header_component: BaseHeaderComponent = operational_utils.make_header_component(client_config, session_manager, CategoryFlag.AUTH, AuthFlags.LOGOUT, finish=end_connection)
    await send_request(writer=writer,
                       header_component=header_component,
                       auth_component=session_manager.auth_component)
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
    
    if response_header.code != SuccessFlags.SUCCESSFUL_SESSION_TERMINATION.value:
        await display(auth_messages.failed_auth_operation(AuthFlags.LOGOUT, response_header.code))
        return
    
    remote_user: str = session_manager.identity
    session_manager.clear_auth_data()

    await display(auth_messages.successful_logout(remote_user=remote_user, **(response_body.contents if display_credentials else {})))

async def change_password(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                          new_password: str,
                          client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager) -> None:
    if not (session_manager.auth_component.token and session_manager.auth_component.refresh_digest):
        await display(auth_messages.invalid_user_data(ValidationError("Token and refresh digest required")))
        return
    try:
        auth_component: BaseAuthComponent = BaseAuthComponent(identity=session_manager.identity, password=new_password,
                                                              token=session_manager.auth_component.token, refresh_digest=session_manager.auth_component.refresh_digest)
    except ValidationError as v:
        await display(auth_messages.invalid_user_data(v))
        return

    await send_request(writer,
                       header_component=BaseHeaderComponent(version=client_config.version, category=CategoryFlag.AUTH, subcategory=AuthFlags.CHANGE_PASSWORD),
                       auth_component=auth_component)
    
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)

    if response_header.code != SuccessFlags.SUCCESSFUL_PASSWORD_CHANGE.value:
        await display(auth_messages.failed_auth_operation(AuthFlags.CHANGE_PASSWORD, response_header.code))
        return

    # Successful password changes require reauthorization
    session_manager.clear_auth_data()
    await display(response_body.contents.get('message', 'Remote session terminated, please reauthorize...'))

import asyncio
from typing import Sequence

from client import session_manager
from client.config import constants as client_constants
from client.cmd.cmd_utils import display
from client.cmd.message_strings import permission_messages, general_messages
from client.communication.incoming import process_response
from client.communication.outgoing import send_request
from client.communication import utils as comms_utils

from models.permissions import RoleTypes, ROLE_MAPPING
from models.response_codes import SuccessFlags
from models.request_model import BasePermissionComponent, BaseHeaderComponent
from models.flags import CategoryFlag, PermissionFlags

async def grant_permission(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                           permission_component: BasePermissionComponent, role: RoleTypes,
                           client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                           end_connection: bool = False) -> None:
    if role == RoleTypes.OWNER:
        raise ValueError('GRANT permission cannot be used to change ownership of a file')
    
    subcategory_bits: int = PermissionFlags.GRANT.value
    for perm_flag, role_type in ROLE_MAPPING.items():
        if role == role_type:
            subcategory_bits |= perm_flag
            break
    else:
        raise ValueError('Invalid role')
    
    header_component: BaseHeaderComponent = comms_utils.make_header_component(client_config=client_config,
                                                                              session_manager=session_manager,
                                                                              category=CategoryFlag.PERMISSION,
                                                                              subcategory=subcategory_bits,
                                                                              finish=end_connection)
    await send_request(writer=writer,
                       header_component=header_component,
                       auth_component=session_manager.auth_component,
                       body_component=permission_component)
    response_header, _ = await process_response(reader, writer, client_config.read_timeout)

    if response_header.code != SuccessFlags.SUCCESSFUL_GRANT.value:
        await display(permission_messages.failed_permission_operation(permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user, response_header.code))
        return
    
    await display(permission_messages.successful_granted_role(permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user,
                                                              permission=ROLE_MAPPING[PermissionFlags(subcategory_bits & PermissionFlags.ROLE_EXTRACTION_BITMASK.value)].value))

async def revoke_permission(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                            permission_component: BasePermissionComponent,
                            client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                            end_connection: bool = False) -> None:
    header_component: BaseHeaderComponent = comms_utils.make_header_component(client_config, session_manager, CategoryFlag.PERMISSION, PermissionFlags.REVOKE)
    await send_request(writer=writer,
                       header_component=header_component,
                       auth_component=session_manager.auth_component,
                       body_component=permission_component)
    
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)

    if response_header.code != SuccessFlags.SUCCESSFUL_REVOKE.value:
        await display(permission_messages.failed_permission_operation(permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user, response_header.code))
        return
    
    await display(permission_messages.successful_revoked_role(permission_component.subject_file_owner, permission_component.subject_file, response_body.contents))

async def transfer_ownership(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                             permission_component: BasePermissionComponent,
                             client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                             end_connection: bool = False) -> str:
    await send_request(writer,
                       BaseHeaderComponent(version=client_config.version, category=CategoryFlag.PERMISSION, subcategory=PermissionFlags.TRANSFER, finish=end_connection),
                       session_manager.auth_component,
                       permission_component)
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_OWNERSHIP_TRANSFER.value:
        await display(permission_messages.failed_permission_operation(permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user, response_body.code))
        return
    
    new_fpath: str = response_body.contents.get('new_filepath')
    if not new_fpath:
        await display(general_messages.missing_response_claim('new_filepath'))
    
    transfer_iso_datetime: str = response_body.contents.get('transfer_datetime')
    if not transfer_iso_datetime:
        await display(general_messages.missing_response_claim('transfer_datetime'))
    
    await display(permission_messages.successful_ownership_trasnfer(permission_component.subject_file_owner, permission_component.subject_file, new_fpath, transfer_iso_datetime, response_header.code))

async def publicise_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                                permission_component: BasePermissionComponent,
                                client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                                end_connection: bool = False) -> None:
    header_component: BaseHeaderComponent = comms_utils.make_header_component(client_config, session_manager, CategoryFlag.PERMISSION, PermissionFlags.PUBLICISE, finish=end_connection)
    await send_request(writer=writer,
                       header_component=header_component,
                       auth_component=session_manager.auth_component,
                       body_component=permission_component)
    
    response_header, _ = await process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_FILE_PUBLICISE.value:
        await display(permission_messages.failed_permission_operation(permission_component.subject_file_owner, permission_component.subject_file, code=response_header.code))
        return
    
    await display(permission_messages.successful_file_publicise(permission_component.subject_file_owner, permission_component.subject_file, response_header.code))

async def hide_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                           permission_component: BasePermissionComponent,
                           client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                           end_connection: bool = False):
    await send_request(writer,
                       BaseHeaderComponent(version=client_config.version, category=CategoryFlag.PERMISSION, subcategory=PermissionFlags.HIDE, finish=end_connection),
                       session_manager.auth_component,
                       permission_component)
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_FILE_PUBLICISE.value:
        await display(permission_messages.failed_permission_operation(permission_component.subject_file_owner, permission_component.subject_file, code=response_header.code))
        return
    
    revoked_info: list[dict[str, str]] = response_body.get('revoked_grantee_info')
    if not revoked_info:
        await display(general_messages.malformed_response_body('revoked_grantee_info'))
    
    # No need to check inner types, anything over a byte stream can be used in f-strings anyways.
    # Although hinted as a list, any Sequence subclass passes as we only need to iterate over it
    elif not (isinstance(revoked_info, Sequence) and all(isinstance(i, dict) for i in revoked_info)):
        await display(general_messages.malformed_response_body("Mismatched data types in response body sent by server"))
        return

    await display(permission_messages.successful_file_hide(permission_component.subject_file_owner, permission_component.subject_file, revoked_info))

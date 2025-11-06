'''Methods corresponding to permisison operations'''

import asyncio
from typing import Sequence, Optional

from client import session_manager
from client.auxillary import operational_utils
from client.config import constants as client_constants
from client.cmd.cmd_utils import display
from client.cmd.message_strings import permission_messages, general_messages
from client.communication.incoming import process_response
from client.communication.outgoing import send_request

from models.permissions import RoleTypes, ROLE_MAPPING
from models.response_codes import SuccessFlags, ClientErrorFlags, ServerErrorFlags
from models.request_model import BasePermissionComponent, BaseHeaderComponent
from models.flags import CategoryFlag, PermissionFlags

__all__ = ('grant_permission',
           'revoke_permission',
           'publicise_remote_file',
           'hide_remote_file')

async def grant_permission(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                           permission_component: BasePermissionComponent, role: RoleTypes,
                           client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                           end_connection: bool = False) -> None:
    if role == RoleTypes.OWNER:
        raise ValueError('GRANT permission cannot be used to change ownership of a file')
    if not permission_component.subject_user:
        raise ValueError('Missing subject user')
    
    subcategory_bits: int = PermissionFlags.GRANT
    for perm_flag, role_type in ROLE_MAPPING.items():
        if role == role_type:
            subcategory_bits |= perm_flag
            break
    else:
        raise ValueError('Invalid role')
    
    header_component: BaseHeaderComponent = operational_utils.make_header_component(client_config=client_config,
                                                                                    session_manager=session_manager,
                                                                                    category=CategoryFlag.PERMISSION,
                                                                                    subcategory=subcategory_bits,
                                                                                    finish=end_connection)
    await send_request(writer=writer,
                       header_component=header_component,
                       auth_component=session_manager.auth_component,
                       body_component=permission_component)
    response_header, _ = await process_response(reader, writer, client_config.read_timeout)

    if response_header.code != SuccessFlags.SUCCESSFUL_GRANT:
        assert isinstance(response_header.code, (ClientErrorFlags, ServerErrorFlags))
        await display(permission_messages.failed_permission_operation(permission_component.subject_file_owner,
                                                                      permission_component.subject_file,
                                                                      permission_component.subject_user,
                                                                      response_header.code))
        return

    await display(permission_messages.successful_granted_role(permission_component.subject_file_owner,
                                                              permission_component.subject_file,
                                                              permission_component.subject_user,
                                                              permission=ROLE_MAPPING[PermissionFlags(subcategory_bits & PermissionFlags.ROLE_EXTRACTION_BITMASK.value)].value))

async def revoke_permission(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                            permission_component: BasePermissionComponent,
                            client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                            end_connection: bool = False) -> None:
    header_component: BaseHeaderComponent = operational_utils.make_header_component(client_config, session_manager,
                                                                                    CategoryFlag.PERMISSION, PermissionFlags.REVOKE)
    await send_request(writer=writer,
                       header_component=header_component,
                       auth_component=session_manager.auth_component,
                       body_component=permission_component)
    
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)

    if response_header.code != SuccessFlags.SUCCESSFUL_REVOKE:
        assert isinstance(response_header.code, (ClientErrorFlags, ServerErrorFlags))
        await display(permission_messages.failed_permission_operation(permission_component.subject_file_owner, permission_component.subject_file,
                                                                      permission_component.subject_user, response_header.code))
        return
    
    await display(permission_messages.successful_revoked_role(permission_component.subject_file_owner, permission_component.subject_file,
                                                              response_body.contents if (response_body and response_body.contents) else {}))

async def transfer_ownership(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                             permission_component: BasePermissionComponent,
                             client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                             end_connection: bool = False) -> Optional[str]:
    header_component: BaseHeaderComponent = operational_utils.make_header_component(client_config, session_manager, CategoryFlag.PERMISSION, PermissionFlags.TRANSFER, finish=end_connection)
    await send_request(writer=writer,
                       header_component=header_component,
                       auth_component=session_manager.auth_component,
                       body_component=permission_component)
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_OWNERSHIP_TRANSFER:
        assert isinstance(response_header.code, (ClientErrorFlags, ServerErrorFlags))
        await display(permission_messages.failed_permission_operation(permission_component.subject_file_owner, permission_component.subject_file, permission_component.subject_user, response_header.code))
        return
    
    if not (response_body and response_body.contents):
        await display(general_messages.malformed_response_body('Missing response claims'))
        return

    new_fpath, transfer_iso_datetime = await operational_utils.filter_claims(response_body.contents, "new_filepath", "transfer_datetime")    
    await display(permission_messages.successful_ownership_trasnfer(remote_directory=permission_component.subject_file_owner,
                                                                    remote_file=permission_component.subject_file,
                                                                    new_fpath=new_fpath,
                                                                    datetime_string=transfer_iso_datetime))

async def publicise_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                                permission_component: BasePermissionComponent,
                                client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                                end_connection: bool = False) -> None:
    header_component: BaseHeaderComponent = operational_utils.make_header_component(client_config, session_manager, CategoryFlag.PERMISSION, PermissionFlags.PUBLICISE, finish=end_connection)
    await send_request(writer=writer,
                       header_component=header_component,
                       auth_component=session_manager.auth_component,
                       body_component=permission_component)
    
    response_header, _ = await process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_FILE_PUBLICISE:
        assert isinstance(response_header.code, (ClientErrorFlags, ServerErrorFlags))
        await display(permission_messages.failed_permission_operation(permission_component.subject_file_owner, permission_component.subject_file,
                                                                      code=response_header.code))
        return
    
    assert isinstance(response_header.code, SuccessFlags)
    await display(permission_messages.successful_file_publicise(permission_component.subject_file_owner, permission_component.subject_file, response_header.code))

async def hide_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                           permission_component: BasePermissionComponent,
                           client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                           end_connection: bool = False):
    header_component: BaseHeaderComponent = operational_utils.make_header_component(client_config, session_manager, CategoryFlag.PERMISSION, PermissionFlags.HIDE, finish=end_connection)
    await send_request(writer=writer,
                       header_component=header_component,
                       auth_component=session_manager.auth_component,
                       body_component=permission_component)
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_FILE_HIDE:
        assert isinstance(response_header.code, (ClientErrorFlags, ServerErrorFlags))
        await display(permission_messages.failed_permission_operation(permission_component.subject_file_owner, permission_component.subject_file, code=response_header.code))
        return

    await display(permission_messages.successful_file_hide(permission_component.subject_file_owner, permission_component.subject_file))

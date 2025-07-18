import asyncio
from typing import Optional, Sequence

from client.config import constants as client_constants
from client import session_manager
from client.cmd.cmd_utils import display
from client.cmd.message_strings import permission_messages, general_messages
from client.communication.incoming import process_response
from client.communication.outgoing import send_request

from models.constants import REQUEST_CONSTANTS
from models.permissions import RoleTypes, ROLE_MAPPING
from models.response_codes import SuccessFlags
from models.request_model import BasePermissionComponent, BaseHeaderComponent
from models.flags import CategoryFlag, PermissionFlags

async def grant_permission(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                           granted_role: RoleTypes, remote_user: str, remote_directory: str, remote_file: str,
                           client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,
                           duration: Optional[float] = None):
    subcategory_bits: int = PermissionFlags.GRANT.value
    # Based on role arg, mask the 3 most significant bits
    for flag_equivalent, role in ROLE_MAPPING.items():
        if granted_role == role:
            subcategory_bits |= flag_equivalent.value
            break
    
    header_component: BaseHeaderComponent = BaseHeaderComponent(version=client_config.version, category=CategoryFlag.PERMISSION, subcategory=subcategory_bits)
    if duration:
        duration = min(REQUEST_CONSTANTS.permission.effect_duration_range[1], abs(duration))    # 0th index contains lower bound, 1st index contains upper bound
    
    permission_component: BasePermissionComponent = BasePermissionComponent(subject_file=remote_file, subject_file_owner=remote_directory, subject_user=remote_user, effect_duration=duration)

    await send_request(writer, header_component, session_manager.auth_component, permission_component)
    response_header, _ = await process_response(reader, writer, client_config.read_timeout)

    if response_header.code != SuccessFlags.SUCCESSFUL_GRANT.value:
        await display(permission_messages.failed_permission_operation(remote_directory, remote_file, remote_user, response_header.code))
        return
    
    await display(permission_messages.successful_granted_role(remote_directory, remote_file, remote_user, granted_role.value))

async def revoke_permission(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                            remote_user: str, remote_directory: str, remote_file: str,
                            client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager,) -> None:
    header_component: BaseHeaderComponent = BaseHeaderComponent(version=client_config.version, category=CategoryFlag.PERMISSION, subcategory=PermissionFlags.REVOKE)
    permission_component: BasePermissionComponent = BasePermissionComponent(subject_file=remote_file, subject_file_owner=remote_directory, subject_user=remote_user)

    await send_request(writer, header_component, session_manager.auth_component, permission_component)
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)

    if response_header.code != SuccessFlags.SUCCESSFUL_REVOKE.value:
        await display(permission_messages.failed_permission_operation(remote_directory, remote_file, remote_user, response_body.code))
        return
    
    await display(permission_messages.successful_revoked_role(remote_directory, remote_file, response_body))

async def transfer_ownership(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                             remote_user: str, remote_directory: str, remote_file: str,
                             client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager) -> str:
    header_component: BaseHeaderComponent = BaseHeaderComponent(version=client_config.version, category=CategoryFlag.PERMISSION, subcategory=PermissionFlags.TRANSFER)
    permission_component: BasePermissionComponent = BasePermissionComponent(subject_file=remote_file, subject_file_owner=remote_directory, subject_user=remote_user)

    await send_request(writer, header_component, session_manager.auth_component, permission_component)
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_OWNERSHIP_TRANSFER.value:
        await display(permission_messages.failed_permission_operation(remote_directory, remote_file, remote_user, response_body.code))
        return
    
    new_fpath: str = response_body.contents.get('new_filepath')
    if not new_fpath:
        await display(general_messages.missing_response_claim('new_filepath'))
    
    transfer_iso_datetime: str = response_body.contents.get('transfer_datetime')
    if not transfer_iso_datetime:
        await display(general_messages.missing_response_claim('transfer_datetime'))
    
    await display(permission_messages.successful_ownership_trasnfer(remote_directory, remote_file, new_fpath, transfer_iso_datetime, response_header.code))

async def publicise_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                                remote_directory: str, remote_file: str,
                                client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager) -> None:
    header_component: BaseHeaderComponent = BaseHeaderComponent(version=client_config.version, category=CategoryFlag.PERMISSION, subcategory=PermissionFlags.PUBLICISE)
    permission_component: BasePermissionComponent = BasePermissionComponent(subject_file=remote_file, subject_file_owner=remote_directory)

    await send_request(writer, header_component, session_manager.auth_component, permission_component)
    response_header, _ = await process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_FILE_PUBLICISE.value:
        await display(permission_messages.failed_permission_operation(remote_directory, remote_file, code=response_header.code))
        return
    
    await display(permission_messages.successful_file_publicise(remote_directory, remote_file, response_header.code))

async def hide_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                           remote_directory: str, remote_file: str,
                           client_config: client_constants.ClientConfig, session_manager: session_manager.SessionManager):
    header_component: BaseHeaderComponent = BaseHeaderComponent(version=client_config.version, category=CategoryFlag.PERMISSION, subcategory=PermissionFlags.HIDE)
    permission_component: BasePermissionComponent = BasePermissionComponent(subject_file=remote_file, subject_file_owner=remote_directory)

    await send_request(writer, header_component, session_manager.auth_component, permission_component)
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_FILE_PUBLICISE.value:
        await display(permission_messages.failed_permission_operation(remote_directory, remote_file, code=response_header.code))
        return
    
    revoked_info: list[dict[str, str]] = response_body.get('revoked_grantee_info')
    if not revoked_info:
        await display(general_messages.malformed_response_body('revoked_grantee_info'))
    
    # No need to check inner types, anything over a byte stream can be used in f-strings anyways.
    # Although hinted as a list, any Sequence subclass passes as we only need to iterate over it
    elif not (isinstance(revoked_info, Sequence) and all(isinstance(i, dict) for i in revoked_info)):
        await display(general_messages.malformed_response_body("Mismatched data types in response body sent by server"))
        return

    await display(permission_messages.successful_file_hide(remote_directory, remote_file, revoked_info))

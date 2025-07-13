import asyncio
import aiofiles
from typing import Optional

from client.bootup import session_manager
from client.cmd_utils import display
from client.communication.incoming import process_response
from client.communication.outgoing import send_request
from client.config.constants import CLIENT_CONFIG

from models.constants import REQUEST_CONSTANTS
from models.permissions import RoleTypes, ROLE_MAPPING
from models.response_codes import SuccessFlags
from models.request_model import BasePermissionComponent, BaseHeaderComponent
from models.flags import CategoryFlag, PermissionFlags

async def grant_permission(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, granted_role: RoleTypes, remote_user: str, remote_directory: str, remote_file: str, duration: Optional[float] = None):
    subcategory_bits: int = PermissionFlags.GRANT.value
    # Based on role arg, mask the 3 most significant bits
    for flag_equivalent, role in ROLE_MAPPING.items():
        if granted_role == role:
            subcategory_bits |= flag_equivalent.value
            break
    
    header_component: BaseHeaderComponent = BaseHeaderComponent(version=CLIENT_CONFIG.version, category=CategoryFlag.PERMISSION, subcategory=subcategory_bits)
    if duration:
        duration = min(REQUEST_CONSTANTS.permission.effect_duration_range[1], abs(duration))    # 0th index contains lower bound, 1st index contains upper bound
    
    file_component: BasePermissionComponent = BasePermissionComponent(subject_file=remote_file, subject_file_owner=remote_directory, subject_user=remote_user, effect_duration=duration)

    await send_request(writer, header_component, session_manager.auth_component, file_component)
    response_header, _ = await process_response(reader, writer, CLIENT_CONFIG.read_timeout, REQUEST_CONSTANTS.header.max_bytesize)

    if response_header.code != SuccessFlags.SUCCESSFUL_GRANT.value:
        raise Exception

async def revoke_permission(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, remote_user: str, remote_directory: str, remote_file: str) -> None:
    header_component: BaseHeaderComponent = BaseHeaderComponent(version=CLIENT_CONFIG.version, category=CategoryFlag.PERMISSION, subcategory=PermissionFlags.REVOKE)
    file_component: BasePermissionComponent = BasePermissionComponent(subject_file=remote_file, subject_file_owner=remote_directory, subject_user=remote_user)

    await send_request(writer, header_component, session_manager.auth_component, file_component)
    response_header, response_body = await process_response(reader, writer, CLIENT_CONFIG.read_timeout, REQUEST_CONSTANTS.header.max_bytesize)

    if response_header.code != SuccessFlags.SUCCESSFUL_REVOKE.value:
        raise Exception
    
    await display(f'Revoked role data: {response_body["revoked_role_data"]}')

async def transfer_ownership():
    ...

async def publicise_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, remote_directory: str, remote_file: str) -> None:
    header_component: BaseHeaderComponent = BaseHeaderComponent(version=CLIENT_CONFIG.version, category=CategoryFlag.PERMISSION, subcategory=PermissionFlags.PUBLICISE)
    file_component: BasePermissionComponent = BasePermissionComponent(subject_file=remote_file, subject_file_owner=remote_directory)

    await send_request(writer, header_component, session_manager.auth_component, file_component)
    response_header, _ = await process_response(reader, writer, CLIENT_CONFIG.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_FILE_PUBLICISE.value:
        await display(f'Failed to publicise file {remote_directory}/{remote_file}.\n Code: {response_header.code}')
        return
    
    await display(f'{response_header.code}: Publicised file {remote_directory}/{remote_file}, all remote users now have read access')


async def hide_remote_file(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, remote_directory: str, remote_file: str):
    header_component: BaseHeaderComponent = BaseHeaderComponent(version=CLIENT_CONFIG.version, category=CategoryFlag.PERMISSION, subcategory=PermissionFlags.PUBLICISE)
    file_component: BasePermissionComponent = BasePermissionComponent(subject_file=remote_file, subject_file_owner=remote_directory)

    await send_request(writer, header_component, session_manager.auth_component, file_component)
    response_header, _ = await process_response(reader, writer, CLIENT_CONFIG.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_FILE_PUBLICISE.value:
        await display(f'Failed to hide file {remote_directory}/{remote_file}.\n Code: {response_header.code}')
        return
    
    await display(f'{response_header.code}: Hid file {remote_directory}/{remote_file}, all remote users with public read access have had their permissions revoked.\nNote that remote users with permissions granted outside of publicity have not been affected')


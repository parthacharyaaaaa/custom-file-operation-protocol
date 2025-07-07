import os

from response_codes import SuccessFlags
from models.response_models import ResponseHeader, ResponseBody
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BaseFileComponent

from server.bootup import user_master, file_locks, delete_cache, read_cache, write_cache, append_cache
from server.config import ServerConfig
from server.file_ops.base_operations import read_file, delete_file
from server.errors import InsufficientPermissions, FileConflict
from server.permission_ops.permission_operations import check_file_permission
from server.database.models import role_types

import orjson

async def handle_deletion(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, file_component: BaseFileComponent) -> tuple[ResponseHeader, None]:
    # Make sure request is coming from file owner
    if file_component.subject_file_owner != auth_component.identity:
        raise InsufficientPermissions(f'Missing permission to delete file {file_component.subject_file} owned by {file_component.subject_file_owner}')
    # Validate against session, in case of tampered auth component
    if not user_master.authenticate_session(username=auth_component.identity, token=auth_component.token):
        # TODO: Add logging for tampered auth component
        raise InsufficientPermissions(f'The demon of Babylon disguises himself with the coat of the righteous')
    
    # Request validated. No need to acquire lock since owner's deletion request is more important than any concurrent file amendment locks
    file: os.PathLike = os.path.join(file_component.subject_file_owner, file_component.subject_file)
    file_locks[file] = None

    file_deleted: bool = await delete_file(ServerConfig.ROOT.value, file, delete_cache, append_cache, read_cache, write_cache)
    if not file_deleted:
        raise FileConflict(f'Failed to delete file {file_component.subject_file}')
    
    return (ResponseHeader(version=header_component.version, code=SuccessFlags.SUCCESSFUL_FILE_DELETION.value, ended_connection=header_component.finish),
            None)

async def handle_amendment(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, file_component: BaseFileComponent) -> tuple[ResponseHeader, ResponseBody]:
    ...

async def handle_read(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, file_component: BaseFileComponent) -> tuple[ResponseHeader, ResponseBody]:
    # Authetenticate session
    if not user_master.authenticate_session(username=auth_component.identity, token=auth_component.token):
        raise InsufficientPermissions(f'Invalid session and/or auth component for user {auth_component.identity}')
    
    # Check permissions
    if not check_file_permission(filename=file_component.subject_file, owner=file_component.subject_file_owner, grantee=auth_component.identity, check_for=role_types):
        raise InsufficientPermissions(f'User {auth_component.identity} does not have read permission on file {file_component.subject_file} owned by {file_component.subject_file_owner}')
    
    fpath: os.PathLike = os.path.join(file_component.subject_file_owner, file_component.subject_file)
    read_data, cursor_position, eof_reached = await read_file(root=ServerConfig.ROOT.value, fpath=fpath,
                                                              deleted_cache=delete_cache, read_cache=read_cache,
                                                              cursor_position=file_component.cursor_position, nbytes=file_component.chunk_size, reader_keepalive=file_component.cursor_keepalive,
                                                              purge_reader=header_component.finish, identifier=auth_component.identity, cached=True)
    
    return (ResponseHeader(version=header_component.version, code=SuccessFlags.SUCCESSFUL_READ, ended_connection=header_component.finish),
            ResponseBody(contents=orjson.dumps({'read' : read_data}), return_partial=not eof_reached, chunk_number=file_component.chunk_number+1, keepalive_accepted=bool(read_cache.get(fpath)))) 

async def handle_creation(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent, file_component: BaseFileComponent) -> tuple[ResponseHeader, None]:
    ...
import asyncio
import time

from models.request_model import BaseHeaderComponent, BaseAuthComponent
from models.response_codes import SuccessFlags
from models.response_models import ResponseHeader, ResponseBody
from models.session_metadata import SessionMetadata

from server.authz import user_manager
from server.config import server_config
from server.errors import InvalidAuthSemantic
from server.file_ops.base_operations import delete_directory
from server.logging import enqueue_log

__all__ = ('handle_registration', 'handle_login', 'handle_deletion', 'handle_password_change', 'handle_session_refresh', 'handle_session_termination')

async def handle_registration(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent,
                              config: server_config.ServerConfig, user_manager: user_manager.UserManager) -> tuple[ResponseHeader, None]:
    if not auth_component.auth_logical_check('authorization'):
        raise InvalidAuthSemantic('Account creation requires only the following fields: identity, password')
    
    await user_manager.create_user(username=auth_component.identity, password=auth_component.password, make_dir=True, root=config.root_directory)

    return (ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_USER_CREATION.value, ended_connection=header_component.finish, config=config),
            ResponseBody(contents={'epoch' : time.time(), 'username' : auth_component.identity}))

async def handle_login(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent,
                       config: server_config.ServerConfig, user_manager: user_manager.UserManager) -> tuple[ResponseHeader, ResponseBody]:
    if not auth_component.auth_logical_check('authorization'):
        raise InvalidAuthSemantic('Login requires only the following fields: identity, password')
    
    session_metadata: SessionMetadata = await user_manager.authorize_session(username=auth_component.identity, password=auth_component.password)
    header: ResponseHeader = ResponseHeader.from_server(config=config, code=SuccessFlags.SUCCESSFUL_AUTHENTICATION.value, ended_connection=header_component.finish)
    body: ResponseBody = ResponseBody(contents={'session' : session_metadata.dict_repr})

    return header, body

async def handle_deletion(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent,
                          config: server_config.ServerConfig, user_manager: user_manager.UserManager,
                          *caches) -> tuple[ResponseHeader, ResponseBody]:
    await user_manager.authenticate_session(username=auth_component.identity, token=auth_component.token, raise_on_exc=True)

    await user_manager.delete_user(auth_component.identity, auth_component.password,
                                  *caches)
    
    # Delete this user's directory
    files_deleted = await asyncio.wait_for(asyncio.to_thread(delete_directory, root=config.root_directory, dirname=auth_component.identity),
                                           timeout=config.file_transfer_timeout)
    
    header: ResponseHeader = ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_USER_DELETION, ended_connection=header_component.finish, config=config)
    body = ResponseBody(contents={'deleted_count' : len(files_deleted),
                                  'deleted_files' : files_deleted})

    return header, body

async def handle_password_change(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent,
                                 config: server_config.ServerConfig, user_manager: user_manager.UserManager) -> tuple[ResponseHeader, ResponseBody]:
    await user_manager.authenticate_session(username=auth_component.identity, token=auth_component.token, raise_on_exc=True)
    await user_manager.change_password(username=auth_component, new_password=auth_component.password)

    # Terminate session and require reauthentication
    user_manager.session.pop(auth_component.identity, None)
    user_manager.previous_digests_mapping.pop(auth_component.identity, None)
    header: ResponseHeader = ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_PASSWORD_CHANGE.value)
    body = ResponseBody(contents={'message' : f'Reauthentication required'})

    return header, body

async def handle_session_refresh(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent,
                                 config: server_config.ServerConfig, user_manager: user_manager.UserManager) -> tuple[ResponseHeader, ResponseBody]:
    if not auth_component.auth_logical_check('authentication'):
        raise InvalidAuthSemantic('Session refresh requires only the following fields: identity, token, refresh_digest')
    
    # UserManager.refresh_session() implictly authenticates session
    new_digest, iteration = await user_manager.refresh_session(username=auth_component.identity, token=auth_component.token, digest=auth_component.refresh_digest)
    header: ResponseHeader = ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_SESSION_REFRESH.value, ended_connection=header_component.finish, config=config)
    body = ResponseBody(contents={'digest' : new_digest, 'iteration' : iteration})

    return header, body

async def handle_session_termination(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent,
                                     config: server_config.ServerConfig, user_manager: user_manager.UserManager) -> tuple[ResponseHeader, ResponseBody]:
    if not auth_component.auth_logical_check('authentication'):
        raise InvalidAuthSemantic('Session termination requires only the following fields: identity, token, refresh_digest')
    
    await user_manager.authenticate_session(username=auth_component.identity)
    terminated_session: SessionMetadata = await user_manager.terminate_session(username=auth_component.identity, token=auth_component.token)

    termination_time: float = time.time()
    header: ResponseHeader = ResponseHeader.from_server(version=header_component.version, code=SuccessFlags.SUCCESSFUL_SESSION_TERMINATION.value, ended_connection=header_component.finish, config=config)
    body: ResponseBody = ResponseBody(contents={'time_of_logout' : termination_time,
                                                'user' : auth_component.identity,
                                                'last_token' : terminated_session.token,
                                                'session_iterations' : terminated_session.iteration,
                                                'session_lifespan' : terminated_session.lifespan,
                                                'forgone_validity' : terminated_session.valid_until - termination_time})
    return header, body

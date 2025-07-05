import time
import orjson
from server.authz.user_manager import SessionMetadata
from server.bootup import user_master, read_cache, write_cache, append_cache
from server.errors import InvalidAuthSemantic
from models.request_model import BaseHeaderComponent, BaseAuthComponent
from models.response_models import ResponseHeader, ResponseBody
from response_codes import SuccessFlags

async def handle_registration(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent) -> tuple[ResponseHeader, None]:
    if not auth_component.auth_logical_check('authorization'):
        raise InvalidAuthSemantic('Account creation requires only the following fields: identity, password')
    
    await user_master.create_user(username=auth_component.identity, password=auth_component.password, make_dir=True)
    header: ResponseHeader = ResponseHeader(version=header_component.version, code=SuccessFlags.SUCCESSFUL_USER_CREATION.value)

    return header, None

async def handle_login(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent) -> tuple[ResponseHeader, ResponseBody]:
    if not auth_component.auth_logical_check('authorization'):
        raise InvalidAuthSemantic('Login requires only the following fields: identity, password')
    
    session_metadata: SessionMetadata = await user_master.authorize_session(username=auth_component.identity, password=auth_component.password)
    header: ResponseHeader = ResponseHeader(version=header_component.version, code=SuccessFlags.SUCCESSFUL_AUTHENTICATION.value)
    body: ResponseBody = ResponseBody(contents=orjson.dumps({**session_metadata.dict_repr}))

    return header, body

async def handle_deletion(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent) -> tuple[ResponseHeader, ResponseBody]:
    await user_master.delete_user(auth_component.identity, auth_component.password,
                                    read_cache, write_cache, append_cache)
    #TODO: Add deletion method for all of this user's files
    header: ResponseHeader = ResponseHeader(version=header_component.version, code=SuccessFlags.SUCCESSFUL_USER_DELETION)
    body = ResponseBody(contents=f'All files and permissions under user {auth_component.identity} have been deleted')

    return header, body

async def handle_password_change(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent) -> tuple[ResponseHeader, ResponseBody]:
    user_master.authenticate_session(username=auth_component.identity, token=auth_component.token, raise_on_exc=True)
    await user_master.change_password(username=auth_component, new_password=auth_component.password)

    # Terminate session and require reauthentication
    user_master.session.pop(auth_component.identity, None)
    user_master.previous_digests_mapping.pop(auth_component.identity, None)
    header: ResponseHeader = ResponseHeader(version=header_component.version, code=SuccessFlags.SUCCESSFUL_PASSWORD_CHANGE.value)
    body = ResponseBody(contents=f'Reauthentication required')

    return header, body

async def handle_session_refresh(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent) -> tuple[ResponseHeader, ResponseBody]:
    if not auth_component.auth_logical_check('authentication'):
        raise InvalidAuthSemantic('Session refresh requires only the following fields: identity, token, refresh_digest')
    
    # UserManager.refresh_session() implictly authenticates session
    new_digest, iteration = await user_master.refresh_session(username=auth_component.identity, token=auth_component.token, digest=auth_component.refresh_digest)
    header: ResponseHeader = ResponseHeader(version=header_component.version, code=SuccessFlags.SUCCESSFUL_SESSION_REFRESH.value)
    body = ResponseBody(contents=orjson.dumps({'digest' : new_digest, 'iteration' : iteration}))

    return header, body

async def handle_session_termination(header_component: BaseHeaderComponent, auth_component: BaseAuthComponent) -> tuple[ResponseHeader, ResponseBody]:
    if not auth_component.auth_logical_check('authentication'):
        raise InvalidAuthSemantic('Session termination requires only the following fields: identity, token, refresh_digest')
    
    await user_master.authenticate_session(username=auth_component.identity)
    terminated_session: SessionMetadata = await user_master.terminate_session(username=auth_component.identity, token=auth_component.token)

    termination_time: float = time.time()
    header: ResponseHeader = ResponseHeader(version=header_component.version, code=SuccessFlags.SUCCESSFUL_SESSION_TERMINATION.value)
    body: ResponseBody = ResponseBody(contents=orjson.dumps({'time_of_logout' : termination_time, 'user' : auth_component.identity,
                                                             'last_token' : terminated_session.token,
                                                             'session_iterations' : terminated_session.iteration,
                                                             'session_lifespan' : terminated_session.lifespan,
                                                             'forgone_validity' : terminated_session.valid_until - termination_time}))
    return header, body

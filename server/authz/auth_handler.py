import asyncio
import orjson
from server.authz.auth_flags import AuthFlags
from server.authz.user_master import SessionMetadata
from server.bootup import user_master, read_cache, write_cache, append_cache
from server.config import CategoryFlag, ServerConfig
from server.comms_utils.incoming import process_auth
from server.comms_utils.outgoing import send_response
from server.errors import InvalidAuthSemantic, SlowStreamRate, UnsupportedOperation
from server.models.response_models import ResponseHeader
from server.models.request_model import BaseHeaderComponent, BaseAuthComponent
from typing import Optional
from pydantic import ValidationError

async def auth_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, header_component: BaseHeaderComponent) -> Optional[BaseAuthComponent]:
    if not header_component.auth_size:
        # Unauthenticated request, only possible actions are: heartbeat and public file read
        if header_component.category == CategoryFlag.HEARTBEAT or header_component.category == CategoryFlag.FILE_OP:
            return None # Return nothing to indicate unauthenticated
        raise InvalidAuthSemantic('Missing auth component in header, and no unauthenticated operation requested')

    # Auth component exists
    try:
        auth_component: BaseAuthComponent = await process_auth(header_component.auth_size, reader, writer)
    except asyncio.TimeoutError:
        response: ResponseHeader = ResponseHeader.from_unverifiable_data(SlowStreamRate, version=ServerConfig.VERSION.value)
        send_response(writer, response)
        return
    except (asyncio.IncompleteReadError, ValidationError, orjson.JSONDecodeError):
        response: ResponseHeader = ResponseHeader.from_unverifiable_data(InvalidAuthSemantic, version=ServerConfig.VERSION.value)
        send_response(writer, response)
        return
    
    # Auth component verified semantically
    if header_component.category != CategoryFlag.AUTH:  # Request is not an operation related to user auth, return auth_component back to caller
        return auth_component

    # Request is for an auth operation
    if header_component.subcategory not in AuthFlags._value2member_map_:    # R level function name, absolutely vile.
        raise UnsupportedOperation(f'Unsupported operation for category: {CategoryFlag.AUTH._name_}')
    
    if header_component.subcategory == AuthFlags.REGISTER:
        if not getattr(auth_component, 'password', None):
            raise InvalidAuthSemantic('Password is required for account creation')
        await user_master.create_user(username=auth_component.identity, password=auth_component.password, make_dir=True)
    
    elif header_component.subcategory == AuthFlags.LOGIN:
        session_metadata: SessionMetadata = await user_master.authorize_session(username=auth_component.identity, password=auth_component.password)
        return BaseAuthComponent(**(auth_component.model_dump() | {'token' : session_metadata.token, 'refresh_digest' : session_metadata.refresh_digest}))
    
    elif header_component.subcategory == AuthFlags.DELETE:
        await user_master.delete_user(auth_component.identity, auth_component.password,
                                      read_cache, write_cache, append_cache)
    
    elif header_component.subcategory == AuthFlags.CHANGE_PASSWORD:
        user_master.authenticate_session(username=auth_component.identity, token=auth_component.token, raise_on_exc=True)
        await user_master.change_password(username=auth_component, new_password=auth_component.password)
        auth_component.password = None
        return auth_component
    
    # Deal with AUTH operations that do require authentication
    if header_component.subcategory == AuthFlags.REFRESH:
        # UserManager.refresh_session() implictly authenticates session
        new_digest: bytes = await user_master.refresh_session(username=auth_component.identity, token=auth_component.token, digest=auth_component.refresh_digest)
        return BaseAuthComponent(**(auth_component.model_dump() | {'refresh_digest' : new_digest}))
    
    elif header_component.subcategory == AuthFlags.LOGOUT:
        await user_master.authenticate_session(username=auth_component)
        await user_master.terminate_session(username=auth_component.identity, token=auth_component.token)
from typing import Literal

from models.request_model import BaseAuthComponent
from models.response_models import ResponseBody
from models.session_metadata import SessionMetadata

from client.auth.globals import current_auth_component, current_session_metadata, auth_response_schema

import jsonschema

def prepare_authorization_component(identity: str, password: str, operation: Literal['login', 'registration']) -> BaseAuthComponent:
    return BaseAuthComponent(identity=identity, password=password)

def prepare_authentication_component(body: ResponseBody) -> BaseAuthComponent:
    global current_auth_component, current_session_metadata
    jsonschema.validate(body.contents, auth_response_schema, jsonschema.Draft202012Validator)

    current_session_metadata.update_digest(new_digest=body.contents['refresh_digest'])
    current_auth_component.refresh_digest = current_session_metadata.refresh_digest
    return current_auth_component
from models.request_model import BaseAuthComponent
from models.response_models import ResponseBody
from models.session_metadata import SessionMetadata

import jsonschema

class SessionManager:
    def __init__(self, auth_response_schema: str):
        self.auth_response_schema: str = auth_response_schema
        self.identity: str = None
        self.session_metadata: SessionMetadata = None
        self.auth_component: BaseAuthComponent = None

    @staticmethod
    def make_authorization_component(identity: str, password: str) -> BaseAuthComponent:
        return BaseAuthComponent(identity=identity, password=password)

    def prepare_authentication_component(self, body: ResponseBody) -> None:
        jsonschema.validate(body.contents, self.auth_response_schema, jsonschema.Draft202012Validator)

        self.session_metadata.update_digest(new_digest=body.contents['refresh_digest'])
        self.auth_component.refresh_digest = self.session_metadata.refresh_digest
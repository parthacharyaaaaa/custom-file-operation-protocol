from models.request_model import BaseAuthComponent
from models.response_models import ResponseBody
from models.session_metadata import SessionMetadata

class SessionManager:
    def __init__(self):
        self._identity: str = None
        self.session_metadata: SessionMetadata = None
        self.auth_component: BaseAuthComponent = None

    @property
    def identity(self) -> str:
        return self._identity

    @staticmethod
    def make_authorization_component(identity: str, password: str) -> BaseAuthComponent:
        return BaseAuthComponent(identity=identity, password=password)

    def local_authenticate(self, identity: str, token: bytes, digest: bytes, lifespan: float, last_refresh: float, valid_until: float, iteration: int) -> None:
        self.session_metadata = SessionMetadata.from_response(token, digest, lifespan, last_refresh, valid_until, iteration)
        self._identity = identity

    def update_authentication_component(self, digest: bytes) -> None:
        self.session_metadata.update_digest(new_digest=digest)
        self.auth_component.refresh_digest = self.session_metadata.refresh_digest

    def clear_auth_data(self) -> None:
        self.session_metadata = None
        self.auth_component = None
        self.identity = None
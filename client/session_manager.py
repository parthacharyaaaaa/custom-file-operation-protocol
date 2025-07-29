from models.request_model import BaseAuthComponent
from models.session_metadata import SessionMetadata
from models.singletons import SingletonMetaclass

class SessionManager(metaclass=SingletonMetaclass):
    __slots__ = ('_host', '_port', '_identity', '_session_metadata', '_auth_component')

    def __init__(self, host: str, port: int):
        self._host: str = host
        self._port: int = port
        self._identity: str = None
        self._session_metadata: SessionMetadata = None
        self._auth_component: BaseAuthComponent = None

    @property
    def host(self) -> str:
        return self._host
    @property
    def port(self) -> int:
        return self._port
    @property
    def identity(self) -> str:
        return self._identity
    @property
    def session_metadata(self) -> SessionMetadata:
        return self._session_metadata
    @property
    def auth_component(self) -> BaseAuthComponent:
        return self._auth_component

    def local_authenticate(self, identity: str, token: bytes, refresh_digest: bytes, lifespan: float, last_refresh: float, valid_until: float, iteration: int) -> None:
        self._session_metadata = SessionMetadata.from_response(token, refresh_digest, lifespan, last_refresh, valid_until, iteration)
        self._identity = identity
        self._auth_component = BaseAuthComponent(identity=identity, token=token, refresh_digest=refresh_digest)

    def update_authentication_component(self, digest: bytes) -> None:
        self._session_metadata.update_digest(new_digest=digest)
        self._auth_component.refresh_digest = self.session_metadata.refresh_digest

    def clear_auth_data(self) -> None:
        self._session_metadata = None
        self._auth_component = None
        self._identity = None
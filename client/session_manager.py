'''Abstraction for locally managing client session'''
from functools import wraps
from typing import Any, Optional
from ipaddress import IPv4Address, IPv6Address

from models.request_model import BaseAuthComponent
from models.session_metadata import SessionMetadata
from models.singletons import SingletonMetaclass

from pydantic.networks import IPvAnyAddress

__all__ = 'SessionManager',

class SessionManager(metaclass=SingletonMetaclass):
    '''Abstraction for locally managing client session'''
    __slots__ = ('_host', '_port', '_identity', '_session_metadata', '_auth_component', '__weakref__')

    def __init__(self, host: str, port: int):
        self._host: IPvAnyAddress = IPv6Address(host) if ':' in host else IPv4Address(host)
        if not (0 <= port <= 65_535):
            raise ValueError('Invalid port address') 
        self._port: int = port
        self._identity: Optional[str] = None
        self._session_metadata: Optional[SessionMetadata] = None
        self._auth_component: Optional[BaseAuthComponent] = None

    @staticmethod
    def requires_authentication(function):
        @wraps(function)
        def decorated(*args, **kwargs) -> Any:
            if not args:
                raise ValueError(f'Missing self argument')
            
            instance: SessionManager = args[0]
            if not isinstance(instance, SessionManager):
                raise ValueError(f'First positional argument not an instance of {SessionManager.__name__}')
            
            if not (instance._auth_component and instance._session_metadata and instance._identity):
                raise ValueError(f'Invalid authentication state')
            
            return function(*args, **kwargs)
        return decorated

    @property
    def host(self) -> IPvAnyAddress:
        return self._host
    @property
    def port(self) -> int:
        return self._port
    @property
    def identity(self) -> Optional[str]:
        return self._identity
    @property
    def session_metadata(self) -> Optional[SessionMetadata]:
        return self._session_metadata
    @property
    def auth_component(self) -> Optional[BaseAuthComponent]:
        return self._auth_component

    def local_authenticate(self, identity: str, token: bytes, refresh_digest: bytes, lifespan: float, last_refresh: float, valid_until: float, iteration: int) -> None:
        self._session_metadata = SessionMetadata.from_response(token, refresh_digest, lifespan, last_refresh, valid_until, iteration)
        self._identity = identity
        self._auth_component = BaseAuthComponent(identity=identity, token=token, refresh_digest=refresh_digest)

    @requires_authentication
    def reauthorize(self, new_digest: bytes) -> None:
        assert self._auth_component and self._session_metadata  # through requires_authentication decorator
        self._session_metadata.update_digest(new_digest=new_digest)
        self._auth_component.refresh_digest = self._session_metadata._refresh_digest

    def clear_auth_data(self) -> None:
        self._session_metadata = None
        self._auth_component = None
        self._identity = None

    def check_authentication_integrity(self) -> bool:
        return all((self._session_metadata, self._identity, self._auth_component))
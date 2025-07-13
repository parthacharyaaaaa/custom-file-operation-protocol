import time
from typing import Any

class SessionMetadata:
    __slots__ = '_token', '_refresh_digest', '_last_refresh', '_iteration', '_lifespan', '_valid_until'
    # Cryptograhic metadata
    _token: bytes
    _refresh_digest: bytes

    # Chronologic metadata
    _last_refresh: float
    _lifespan: float
    _valid_until: float

    # Additional
    _iteration: int

    @property
    def token(self) -> bytes:
        return self._token
    @property
    def refresh_digest(self) -> bytes:
        return self._refresh_digest
    @property
    def last_refresh(self) -> float:
        return self._last_refresh
    @property
    def iteration(self) -> int:
        return self._iteration
    @property
    def lifespan(self) -> float:
        return self._lifespan
    @property
    def valid_until(self) -> float:
        return self._valid_until
    
    @property
    def dict_repr(self) -> dict[str, Any]:
        return {'token' : self.token,
                'refresh_digest' : self.refresh_digest,
                'lifespan' : self.lifespan,
                'valid_until' : self.valid_until,
                'iteration' : self.iteration}
    
    @property
    def json_repr(self) -> dict[str, Any]:
        return {'token' : self.token.hex(),
                'refresh_digest' : self.refresh_digest.hex(),
                'lifespan' : self.lifespan,
                'valid_until' : self.valid_until,
                'iteration' : self.iteration}

    def __init__(self, token: bytes, refresh_digest: bytes, lifespan: float):
        self._token = token
        self._refresh_digest = refresh_digest
        self._last_refresh = time.time()
        self._lifespan = lifespan
        self._valid_until = self._last_refresh + lifespan
        self._iteration = 1
    
    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}({self.token}, {self.refresh_digest}, {self.lifespan}) at location {id(self)}>'
    
    def update_digest(self, new_digest: bytes) -> None:
        self._refresh_digest = new_digest
        self._last_refresh = time.time()
        self.valid_until = self._last_refresh + self.lifespan
        self._iteration+=1

    def get_validity(self) -> float:
        return self.last_refresh + self.lifespan
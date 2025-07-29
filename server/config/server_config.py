from typing import Annotated
from typing_extensions import Self
from models.constants import REQUEST_CONSTANTS
from pydantic import BaseModel, Field, IPvAnyAddress, model_validator, ValidationError

__all__ = ('ServerConfig',)

class ServerConfig(BaseModel):
    version: Annotated[str, Field(frozen=True, pattern=rf'{REQUEST_CONSTANTS.header.version_regex}')]

    # Network
    host: Annotated[IPvAnyAddress, Field(frozen=True)]
    port: Annotated[int, Field(frozen=True)]
    read_timeout: Annotated[float, Field(frozen=True, ge=0)]
    socket_connection_timeout: Annotated[float, Field(frozen=True, ge=0)]

    # Database
    max_connections: tuple[Annotated[int, Field(ge=1)],
                           Annotated[int, Field(ge=1)],
                           Annotated[int, Field(ge=1)]
                           ]
    connection_timeout: Annotated[float, Field(ge=1.0)]
    connection_refresh_interval: Annotated[float, Field(ge=1.0)]
    connection_lease_duration: Annotated[float, Field(ge=1.0)]

    # File
    file_cache_size: Annotated[int, Field(ge=0)]
    file_cache_ttl: Annotated[float, Field(frozen=True, ge=0)]
    file_lock_ttl: Annotated[float, Field(frozen=True, ge=0)]
    file_contention_timeout: Annotated[float, Field(ge=0)]
    file_transfer_timeout: Annotated[float, Field(frozen=True, ge=0)]
    cache_public_files: Annotated[bool, Field(default=False)]
    root_directory: Annotated[str, Field(default='files')]
    user_max_files: Annotated[int, Field(ge=1)]

    # Auth
    max_attempts: Annotated[int, Field(frozen=True, ge=0)]
    lock_timeouts: tuple[Annotated[float, Field(ge=0)],
                         Annotated[float, Field(ge=0)],
                         Annotated[float, Field(ge=0)],
                         Annotated[float, Field(ge=0)]]
    session_lifespan: Annotated[float, Field(ge=0, le=86400)]   # 86400 seconds = 1 day

    # Logging
    log_batch_size: Annotated[int, Field(ge=1)]
    log_interval: Annotated[float, Field(ge=0)]
    log_waiting_period: Annotated[float, Field(ge=0)]


    @model_validator(mode='after')
    def validate_network_timings(self) -> Self:
        if self.socket_connection_timeout <= self.read_timeout:
            raise ValidationError(f'Socket connection timeout {self.socket_connection_timeout} must be greater than component read timeout {self.read_timeout}')
        return self
    
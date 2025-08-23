from pathlib import Path
from functools import partial
from typing import Annotated
from typing_extensions import Self

from models.constants import REQUEST_CONSTANTS

from pydantic import BaseModel, Field, IPvAnyAddress, model_validator, BeforeValidator

__all__ = ('ServerConfig',)

def _ensure_minimum_length(arg: str, length: int, alias: str) -> str:
    if len(arg:=arg.strip()) < length:
        raise ValueError(f'Argument ({alias}, value: {arg}) must have atleast length {length}, got {len(arg)}')
    return arg

class ServerConfig(BaseModel):
    version: Annotated[str, Field(frozen=True, pattern=rf'{REQUEST_CONSTANTS.header.version_regex}')]

    # Network
    host: Annotated[IPvAnyAddress, Field(frozen=True)]
    port: Annotated[int, Field(frozen=True)]
    read_timeout: Annotated[float, Field(frozen=True, ge=0)]
    socket_connection_timeout: Annotated[float, Field(frozen=True, ge=0)]

    # Credentials
    key_filepath: Annotated[Path, BeforeValidator(partial(_ensure_minimum_length, length=4, alias='key_filepath'))]  # Min length 4 to count .pem extension
    certificate_filepath: Annotated[Path, BeforeValidator(partial(_ensure_minimum_length, length=4, alias='certificate_filepath'))]  # Min length 4 to count .crt extension
    rollover_data_filepath: Annotated[Path, BeforeValidator(partial(_ensure_minimum_length, length=5, alias='rollover_data_filepath'))]  # Min length 5 to count .json extension 
    ciphers: Annotated[str, Field(frozen=True), BeforeValidator(lambda ciphers : ciphers.strip().upper())]
    rollover_signature_length: Annotated[int, Field(frozen=True, ge=64)]
    rollover_grace_window: Annotated[float, Field(frozen=True, ge=1)]
    rollover_check_poll_interval: Annotated[float, Field(ge=1)]
    rollover_token_nonce_length: Annotated[int, Field(ge=1, frozen=True)]
    rollover_history_length: Annotated[int, Field(ge=0, frozen=True)]

    # Database
    max_connections: tuple[Annotated[int, Field(ge=1)],
                           Annotated[int, Field(ge=1)],
                           Annotated[int, Field(ge=1)]
                           ]
    connection_timeout: Annotated[float, Field(ge=1.0)]
    connection_refresh_interval: Annotated[float, Field(ge=1.0)]
    connection_lease_duration: Annotated[float, Field(ge=1.0)]

    # File
    files_directory: Annotated[Path, Field(default='files')]
    user_max_files: Annotated[int, Field(ge=1)]
    user_max_storage: Annotated[int, Field(ge=1, frozen=True)]
    file_cache_size: Annotated[int, Field(ge=0)]
    file_cache_ttl: Annotated[float, Field(frozen=True, ge=0)]
    file_lock_ttl: Annotated[float, Field(frozen=True, ge=0)]
    file_contention_timeout: Annotated[float, Field(ge=0)]
    file_transfer_timeout: Annotated[float, Field(frozen=True, ge=0)]
    cache_public_files: Annotated[bool, Field(default=False)]

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
    log_queue_size: Annotated[int, Field(ge=0)]

    @model_validator(mode='after')
    def validate_network_timings(self) -> Self:
        if self.socket_connection_timeout <= self.read_timeout:
            raise ValueError(f'Socket connection timeout {self.socket_connection_timeout} must be greater than component read timeout {self.read_timeout}')
        return self
    
    def finalise_credential_filepaths(self, credentials_directory: Path) -> None:
        if not credentials_directory.is_absolute():
            raise ValueError(f'Directory path {str(credentials_directory)} not absolute')
        
        for path in ['key_filepath', 'certificate_filepath', 'rollover_data_filepath']:
            abs_path: Path = credentials_directory / getattr(self, path)
            setattr(self, path, abs_path)
    
    def update_files_directory(self, server_root: Path) -> None:
        self.files_directory = server_root / self.files_directory
        if not server_root.is_dir():
            raise NotADirectoryError(f'{server_root} not found in local file system')
        elif not server_root.is_absolute():
            raise ValueError('Server root must be an absolute path')

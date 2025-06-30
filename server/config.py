from enum import Enum, IntFlag
import os

class CategoryFlag(IntFlag):
    HEARTBEAT = 0b0001
    AUTH = 0b0010
    FILE_OP = 0b0100
    PERMISSION = 0b1000

class PermissionFlag(IntFlag):
    READ = 0b00001
    WRITE = 0b00010
    DELETE = 0b00100
    GRANT = 0b01000
    OWN = 0b10000

class ServerConfig(Enum):
    # Address
    HOST: str = '127.0.0.1'
    PORT: int = 6090
    ROOT: os.PathLike = os.path.dirname(__file__)

    VERSION: str = '0.0.1'
    VERSION_REGEX: str = r'^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$'
    RESPONSE_CODE_REGEX: str = r'^3\:\*|[0-9]\:[a-z]{1,6}$'
    HEADER_READ_TIMEOUT: float = 1.0
    HEADER_READ_BYTESIZE: int = 200

    AUTH_READ_TIMEOUT: float = 2.0

    FILE_COMP_MAX_BYTESIZE: int = 4096
    AUTH_COMP_MAX_BYTESIZE: int = 1024
    PERM_COMP_MAX_BYTESIZE: int = 512

    # Database
    MAX_CONNECTIONS: tuple[int, int, int] = (30, 20, 10)    # High priority -> low priority
    CONNECTION_OVERFLOW_ALLOWANCE: int = 10     # Applies to all connections
    CONNECTION_TIMEOUT: float = 10
    CONNECTION_REFRESH_TIMER: float = 500
    CONNECTION_LEASE_DURATION: float = 60

    # File I/O
    FILE_CONTENTION_TIMEOUT: float = 5
    FILENAME_REGEX: str = r'^[^\\/]{1,128}\.[a-zA-Z0-9]{2,10}$'
    FILE_CACHE_SIZE: int = 500
    FILE_CACHE_TTL: int = 180
    USER_MAX_FILES: int = 30
    CACHE_PUBLICISED_FILES: bool = True
    CHUNK_MAX_SIZE: int = 4096

    # Auth
    MAX_AUTH_ATTEMPTS: int = 5
    AUTH_LOCK_TIMEOUTS: tuple[int, int, int, int] = (3600, 7200, 42600, 8400)
    PASSWORD_RANGE: tuple[int, int] = (8, 256)
    USERNAME_RANGE: tuple[int, int] = (4, 64)
    USERNAME_REGEX: str = r'^[\w](?:[\w\-]*[\w])?$'
    SESSION_LIFESPAN: int = 10800
    REFRESH_DIGEST_LENGTH = 128

    # Permissions
    EFFECT_DURATION_RANGE: tuple[int, int] = (0, 2_678_400)
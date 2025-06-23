from enum import Enum, IntFlag

class CategoryFlag(IntFlag):
    HEARTBEAT = 0b0001
    AUTH = 0b0010
    FILE_OP = 0b0100
    PERMISSION = 0b1000

class ServerConfig(Enum):
    HEADER_READ_TIMEOUT: float = 1.0
    HEADER_READ_BYTESIZE: int = 32

    # Database
    MAX_CONNECTIONS: tuple[int, int, int] = (30, 20, 10)    # High priority -> low priority
    CONNECTION_OVERFLOW_ALLOWANCE: int = 10     # Applies to all connections
    CONNECTION_TIMEOUT: float = 10
    CONNECTION_REFRESH_TIMER: float = 500

    # File I/O
    FILE_CONTENTION_TIMEOUT: float = 5
    FILE_CACHE_SIZE: int = 500
    FILE_CACHE_TTL: int = 180
    USER_MAX_FILES: int = 30
    CACHE_PUBLICISED_FILES: bool = True

    # Auth
    MAX_AUTH_ATTEMPTS: int = 5
    AUTH_LOCK_TIMEOUTS: tuple[int, int, int, int] = (3600, 7200, 42600, 8400)
    PASSWORD_RANGE: tuple[int, int] = (8, 128)
    USERNAME_RANGE: tuple[int, int] = (4, 64)
    SESSION_LIFESPAN: int = 10800
from enum import Flag

class SuccessFlags(Flag):
    # File I/O
    SUCCESSFUL_FILE_CREATION = "1:fnew"
    SUCCESSFUL_AMEND = "1:amnd"
    SUCCESSFUL_READ = "1:read"
    SUCCESSFUL_FILE_PUBLICISE = "1:pub"
    SUCCESSFUL_FILE_HIDE = "1:hide"
    SUCCESSFUL_FILE_DELETION = "1:fdel"
    SUCCESSFUL_OWNERSHIP_TRANSFER = "1:sft"

    # Auth
    SUCCESSFUL_USER_CREATION = "1:unew"
    SUCCESSFUL_AUTHENTICATION = "1:auth"
    SUCCESSFUL_PASSWORD_CHANGE = "1:pw"
    SUCCESSFUL_SESSION_REFRESH = "1:ref"
    SUCCESSFUL_SESSION_TERMINATION = "1:bye"
    SUCCESSFUL_USER_DELETION = "1:udel"

    # Permissions
    SUCCESSFUL_GRANT = "1:gnt"
    SUCCESSFUL_REVOKE = "1:rvk"
    
    # Heartbeat
    HEARTBEAT = "1:hb"

class IntermediaryFlags(Flag):
    # File I/O
    PARTIAL_AMEND = "0:a"
    PARTIAL_READ = "0:r"

    # General
    WAIT = "0:wait"
    RETRY_NEEDED = "0:retry"

class ClientErrorFlags(Flag):
    # General
    MALFORMED_REQUEST_STRUCTURE = "2:malf"
    NON_JSON_SCHEMA = "2:njs"
    RATE_LIMIT_EXCEEDED = "2:rlex"
    UNACCEPTABLE_SPEED = "2:unsp"
    UNSUPPORTED_OPERATION = "2:unop"
    OPERATIONAL_CONFLICT = "2:opcf"
    OPERATION_CONTESTED = "2:opct"

    # Header related
    INVALID_HEADER_SEMANTIC = "2:ihs"
    INVALID_HEADER_VALUES = "2:ihv"

    # Auth related
    USER_AUTHENTICATION_ERROR = "2:auth"
    INVALID_AUTH_SEMANTIC = "2:ias"
    INCORRECT_AUTH_DATA = "2:iad"
    EXPIRED_AUTH_TOKEN = "2:exp"
    DUPLICATE_LOGIN = "2:dup"
    SESSION_TERMINATED_PREMATURELY = "2:stp"
    BANNED = "2:ban"

    # Body related
    INVALID_BODY_SEMANTIC = "2:ibs"
    INVALID_BODY_VALUE = "2:ibv"

    # File related
    INVALID_FILE_DATA = "2:ifd"
    FILE_NOT_FOUND = "2:nf"
    FILE_CONTESTED = "2:fcnt"
    FILE_CONFLICT = "2:cnf"
    FILE_JUST_DELETED = "2:df"

    # Permissions
    INSUFFICIENT_PERMISSIONS = "2:perm"

    UNKNOWN_EXCEPTION = "2:?"

class ServerErrorFlags(Flag):
    # Umbrella codes
    INTERNAL_SERVER_ERROR = "3:*"
    UNKNOWN_EXCEPTION = "3:?"

    # Server state
    SERVER_TIMEOUT = "3:t"
    SERVER_SHUTDOWN = "3:s"

    # Database related
    DATABASE_FAILURE = "3:db"

    # Hardware failures
    OUT_OF_MEMORY = "3:mem"
    OUT_OF_DISK_SPACE = "3:disk"

CODES: tuple[str] = tuple(k for k, v in (ServerErrorFlags._value2member_map_ | ClientErrorFlags._value2member_map_ | IntermediaryFlags._value2member_map_ | SuccessFlags._value2member_map_).items())
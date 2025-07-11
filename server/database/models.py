from pydantic import BaseModel, Field, IPvAnyAddress
from typing import Annotated, Optional
from datetime import datetime
from enum import Enum, IntFlag

class RoleTypes(Enum):
    OWNER       = 'owner'
    MANAGER     = 'manager'
    READER      = 'reader'
    EDITOR      = 'editor'

class FilePermissions(Enum):
    WRITE           = 'write'
    READ            = 'read'
    DELETE          = 'delete'
    MANAGE_SUPER    = 'manage_super'
    MANAGE_RW       = 'manage_rw'

class Severity(IntFlag):
    INFO                    = 1
    TRACE                   = 2
    ERROR                   = 3
    NON_CRITICAL_FAILURE    = 4
    CRITICAL_FAILURE        = 5

class LogType(Enum):
    '''Python enum mapping to log_type enum in postgres'''
    USER                = 'user'
    DATABASE            = 'database'
    SESSION             = 'session'
    REQUEST             = 'request'
    NETWORK             = 'network'
    INTERNAL            = 'internal'
    PERMISSION          = 'permission'
    AUDIT               = 'audit'
    UNKNOWN             = 'unknown'

class LogAuthor(Enum):
    '''Python enum mapping to logger_type enum in postgres'''
    USER_MASTER         = 'user_master'
    CONNECTION_MASTER   = 'connection_master'
    FILE_HANDLER        = 'file_handler'
    SOCKET_HANDLER      = 'socket_handler'
    BOOTUP_HANDLER      = 'bootup_handler'
    PERMISSION_HANDLER  = 'permission_handler'
    STREAM_PARSER       = 'stream_parser'
    ADMIN               = 'admin'
    CRONJOB             = 'cronjob'
    EXCEPTION_FALLBACK  = 'exception_fallbacl'


class ActivityLog(BaseModel):
    '''Pydantic object mapping to relation ACTIVITY_LOGS'''
    occurance_time: Annotated[datetime, Field(frozen=True, default_factory=datetime.now)]
    severity: Annotated[int, Field(le=5, ge=1, default=1)]
    logged_by: Annotated[LogAuthor, Field(default=LogAuthor.CONNECTION_MASTER.value)]
    log_category: Annotated[LogType, Field(default=LogType.UNKNOWN.value)]
    log_details: Annotated[Optional[str], Field(max_length=512, default=None)]
    user_concerned: Annotated[Optional[str], Field(max_length=128, default=None)]
    host_concerned: Annotated[Optional[IPvAnyAddress], Field(frozen=True, default=None)]
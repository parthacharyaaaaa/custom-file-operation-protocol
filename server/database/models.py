from pydantic import BaseModel, Field, IPvAnyAddress
from typing import Annotated, Optional
from types import MappingProxyType
from datetime import datetime
from enum import Enum

from models.permissions import RoleTypes, FilePermissions

__all__ = ('ROLE_PERMISSION_MAPPING', 'Severity', 'LogType', 'LogAuthor', 'ActivityLog')

ROLE_PERMISSION_MAPPING: MappingProxyType[RoleTypes, tuple[FilePermissions]] = MappingProxyType({
    RoleTypes.READER : (FilePermissions.READ,),
    RoleTypes.EDITOR : (FilePermissions.READ, FilePermissions.WRITE),
    RoleTypes.MANAGER : (FilePermissions.READ, FilePermissions.WRITE, FilePermissions.MANAGE_RW),
    RoleTypes.OWNER : (FilePermissions.READ, FilePermissions.WRITE, FilePermissions.MANAGE_RW, FilePermissions.MANAGE_SUPER, FilePermissions.DELETE)
})

class Severity(Enum):
    INFO                    = 'info'
    TRACE                   = 'trace'
    ERROR                   = 'error'
    NON_CRITICAL_FAILURE    = 'non_critical_failure'
    CRITICAL_FAILURE        = 'critical_failure'

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
    EXCEPTION_FALLBACK  = 'exception_fallback'


class ActivityLog(BaseModel):
    '''Pydantic object mapping to relation ACTIVITY_LOGS'''
    occurance_time: Annotated[datetime, Field(frozen=True, default_factory=datetime.now)]
    reported_severity: Severity
    logged_by: Annotated[LogAuthor, Field(default=LogAuthor.CONNECTION_MASTER)]
    log_category: Annotated[LogType, Field(default=LogType.UNKNOWN)]
    log_details: Annotated[Optional[str], Field(max_length=512, default=None)]
    user_concerned: Annotated[Optional[str], Field(max_length=128, default=None)]
    host_concerned: Annotated[Optional[IPvAnyAddress], Field(frozen=True, default=None)]

    model_config = {
        'use_enum_values' : True
    }
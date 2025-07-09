from pydantic import BaseModel, Field, IPvAnyAddress
from typing import Literal, Annotated, Optional, TypeAlias
from datetime import datetime

role_types: TypeAlias = Literal['owner', 'manager', 'reader', 'editor']

class ActivityLog(BaseModel):
    '''Pydantic object mapping to relation ACTIVITY_LOGS'''
    occurance_time: Annotated[datetime, Field(frozen=True, default_factory=datetime.now)]
    severity: Annotated[int, Field(le=5, ge=1, default=1)]
    logged_by: Annotated[Literal['user_master', 'connection_master', 'file_handler', 'socket_handler', 'bootup_handler', 'permission_handler', 'stream_parser', 'admin', 'cronjob'], Field(default='connection_master')]
    log_category: Annotated[Literal['user', 'database', 'session', 'request', 'network', 'internal', 'permission', 'audit', 'unknown'], Field(default='unknown')]
    log_details: Annotated[Optional[str], Field(max_length=512, default=None)]
    user_concerned: Annotated[Optional[str], Field(max_length=128, default=None)]
    host_concerned: Annotated[Optional[IPvAnyAddress], Field(frozen=True, default=None)]
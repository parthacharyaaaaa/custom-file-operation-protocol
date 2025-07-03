from pydantic import BaseModel, Field, IPvAnyAddress
from typing import Literal, Annotated, Optional
from datetime import datetime

class ActivityLog(BaseModel):
    '''Pydantic object mapping to relation ACTIVITY_LOGS'''
    occurance_time: Annotated[float, Field(frozen=True, default_factory=datetime.now)]
    severity: Annotated[int, Field(le=1, ge=5, default=1)]
    logged_by: Annotated[Literal['session_master', 'connection_master', 'file_handler', 'socket_handler', 'bootup_handler', 'permission_handler', 'stream_parser', 'admin', 'cronjob'], Field(default='internal')]
    log_type: Annotated[Literal['user', 'database', 'session', 'request', 'network', 'internal', 'permission', 'audit', 'unknown'], Field(default='unknown')]
    log_details: Optional[Annotated[str, Field(max_length=512)]]
    user_concerned: Optional[Annotated[str, Field(max_length=128)]]
    host_concerned: Optional[Annotated[IPvAnyAddress, Field(frozen=True)]]
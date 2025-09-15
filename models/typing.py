'''Typing utilities for common protocol models'''
from typing import TypeAlias, Union

from models.flags import AuthFlags, InfoFlags, FileFlags, PermissionFlags
from models.request_model import BaseFileComponent, BaseAuthComponent, BaseHeaderComponent, BasePermissionComponent, BaseInfoComponent
from models.response_codes import SuccessFlags, ClientErrorFlags, ServerErrorFlags

SubcategoryFlag:        TypeAlias = Union[AuthFlags, InfoFlags, FileFlags, PermissionFlags]
ProtocolComponent:      TypeAlias = Union[BaseHeaderComponent, BaseAuthComponent, BaseFileComponent, BasePermissionComponent, BaseInfoComponent]
ResponseCode:           TypeAlias = Union[SuccessFlags, ClientErrorFlags, ServerErrorFlags]
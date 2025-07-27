'''Helper functions for client communcication'''
import time
from typing import Optional, Union

from client.session_manager import SessionManager
from client.config.constants import ClientConfig

from models.request_model import BaseHeaderComponent
from models.flags import CategoryFlag, AuthFlags, PermissionFlags, FileFlags

__all__ = ('make_header_component',)

def make_header_component(client_config: ClientConfig, session_manager: SessionManager,
                          category: CategoryFlag, subcategory: Union[AuthFlags, PermissionFlags, FileFlags] ,
                          auth_size: Optional[int] = 0,
                          body_size: Optional[int] = 0,
                          finish: bool = False) -> BaseHeaderComponent:
    '''Abstraction over BaseHeaderComponent's constructor'''
    return BaseHeaderComponent(version=client_config.version,
                               sender_hostname=session_manager.host,
                               sender_port=session_manager.port,
                               sender_timestamp=time.time(),
                               auth_size=auth_size,
                               body_size=body_size,
                               finish=finish,
                               category=category,
                               subcategory=subcategory)
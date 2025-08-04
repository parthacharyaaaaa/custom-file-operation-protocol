'''Helper functions for client communcication'''
import time
from typing import Any, Optional, Union, Mapping

from client.session_manager import SessionManager
from client.config.constants import ClientConfig

from models.request_model import BaseHeaderComponent
from models.flags import CategoryFlag, AuthFlags, PermissionFlags, FileFlags
from client.cmd.message_strings import general_messages
from client.cmd import cmd_utils

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

async def filter_claims(claimset: Mapping[str, Any], *claims: str, strict: bool = False, default: Any = None) -> list[Any]:
    '''Check a given mapping for claims and return the claims found in the same order in which they were passed'''
    matched_claims: list[Any] = [claimset.get(claim, default) for claim in claims]
    if (len(matched_claims) < len(claims)):
        missing_claims: set[str] = set(claims) - set(matched_claims)
        await cmd_utils.display(general_messages.missing_response_claim(*missing_claims))
        if strict:
            raise ValueError(f'Missing claims ({", ".join(missing_claims)}) in claimset')
    
    return matched_claims
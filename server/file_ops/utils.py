'''Utility methods for file request subhandlers'''
from typing import Optional
from server.config.server_config import ServerConfig

__all__ = ('check_amendmend_storage_integrity',)

def check_amendmend_storage_integrity(content_size: int,
                                      current_file_size: int,
                                      current_storage_used: int,
                                      server_config: ServerConfig,
                                      is_append: bool = False,
                                      cursor_position: Optional[int] = None) -> bool:
    if is_append:
        return current_storage_used + (current_file_size + content_size) <= server_config.user_max_storage
    
    return current_storage_used + (cursor_position or current_file_size) + content_size <= server_config.user_max_storage

'''Module containing IntFlags for request header model (category and subcategory bits)'''
from enum import IntFlag

__all__ = ('CategoryFlag', 'AuthFlags', 'PermissionFlags', 'FileFlags')

class CategoryFlag(IntFlag):
    '''Supported categories for operations'''
    HEARTBEAT = 0b0001
    AUTH = 0b0010
    FILE_OP = 0b0100
    PERMISSION = 0b1000

class AuthFlags(IntFlag):
    '''Supported subcategories for auth-related operations'''
    REGISTER = 0b00000001
    LOGIN = 0b00000010
    REFRESH = 0b00000100
    CHANGE_PASSWORD = 0b00001000
    DELETE = 0b00010000
    LOGOUT = 0b00100000

class PermissionFlags(IntFlag):
    '''Supported subcategories for permission-related operations'''
    # Action (lower nibble)
    GRANT = 0b00000001
    REVOKE = 0b00000010
    HIDE = 0b00000100   # Only allow access by file owner
    PUBLICISE = 0b00001000  # Allow read access by all users
    TRANSFER = 0b00010000   # Transfer ownership entirely. This does not change roles of other grantees
    
    # Optional role for GRANT (reader, editor, manager)
    READER = 0b00100000
    EDITOR = 0b01000000
    MANAGER = 0b10000000
    ROLE_EXTRACTION_BITMASK = 0b11100000

class FileFlags(IntFlag):
    '''Supported subcategories for file-related operations'''
    CREATE      = 0b00000001
    READ        = 0b00000010
    WRITE       = 0b00000100
    OVERWRITE   = 0b00001000
    APPEND      = 0b00010000
    DELETE      = 0b00100000
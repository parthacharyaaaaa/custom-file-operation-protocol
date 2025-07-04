'''Module to provide encapsulation for permission-related subcategory flags'''
from enum import IntFlag

class PermissionFlags(IntFlag):
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

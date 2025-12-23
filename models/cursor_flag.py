from enum import IntFlag

__all__ = ('CursorFlag',
           'CURSOR_BITS_CHECK')

class CursorFlag(IntFlag):
    CURSOR_KEEPALIVE                    = 0b0001
    POST_OPERATION_CURSOR_KEEPALIVE     = 0b0010
    PURGE_CURSOR                        = 0b0100

CURSOR_BITS_CHECK: int = 0
for flag in CursorFlag:
    CURSOR_BITS_CHECK |= flag
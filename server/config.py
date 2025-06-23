from enum import Enum, IntFlag

class CategoryFlag(IntFlag):
    HEARTBEAT = 0b0001
    AUTH = 0b0010
    FILE_OP = 0b0100
    PERMISSION = 0b1000
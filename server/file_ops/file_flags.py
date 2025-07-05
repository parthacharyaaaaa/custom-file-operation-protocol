from enum import IntFlag

class FileFlags(IntFlag):
    CREATE = 0b00000001
    READ = 0b00000010
    WRITE = 0b00000100
    APPEND = 0b00001000
    DELETE = 0b00010000
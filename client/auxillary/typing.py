'''Typing support for client-specific data structures'''

from typing import TypeAlias, Union
import mmap as _mmap

__all__ = ('SupportsBuffer',)

SupportsBuffer: TypeAlias = Union[bytes, bytearray, _mmap.mmap]
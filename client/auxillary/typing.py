from typing import TypeAlias, Union
import mmap as _mmap

SupportsBuffer: TypeAlias = Union[bytes, bytearray, _mmap.mmap]
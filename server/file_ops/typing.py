'''Typing support for file I/O'''

from typing import TypeAlias, Union

from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncBufferedIOBase

from cachetools import TTLCache

__all__ = ('FileBuffer', 'FileBufferCache')

FileBuffer: TypeAlias = Union[AsyncBufferedReader, AsyncBufferedIOBase]

FileBufferCache: TypeAlias = Union[TTLCache[str, dict[str, AsyncBufferedIOBase]],
                                    TTLCache[str, dict[str, AsyncBufferedReader]]]
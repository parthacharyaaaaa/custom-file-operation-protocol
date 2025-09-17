'''Typing support for file I/O'''

from typing import TypeAlias, Union

from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncBufferedIOBase

from cachetools import TTLCache

__all__ = ('FileBuffer', 'FileBufferCacheItem', 'FileBufferCache')

FileBuffer: TypeAlias = Union[AsyncBufferedReader, AsyncBufferedIOBase]

FileBufferCacheItem: TypeAlias = Union[dict[str, AsyncBufferedIOBase],
                                       dict[str, AsyncBufferedReader]]

FileBufferCache: TypeAlias = Union[TTLCache[str, dict[str, AsyncBufferedIOBase]],
                                    TTLCache[str, dict[str, AsyncBufferedReader]]]
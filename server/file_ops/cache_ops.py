'''Basic cache operations to support higher-level `FILE` request handlers and file operations'''

from typing import Literal, Optional, TypeVar
from aiofiles.threadpool.binary import AsyncBufferedIOBase, AsyncBufferedReader
from cachetools import TTLCache
from server.file_ops.typing import FileBufferCacheItem, FileBufferCache

__all__ = ('remove_buffer', 'get_buffer', 'rename_buffers', 'purge_buffers')

T = TypeVar('T', AsyncBufferedIOBase, AsyncBufferedReader)

def remove_buffer(read_cache: FileBufferCache,
                  fpath: str, identifier: str) -> None:
    try:
        read_cache[fpath].pop(identifier, None)
    except KeyError:
        return None
    
def get_buffer(buffer_cache: TTLCache[str, dict[str, T]],
               fpath: str, identifier: str) -> Optional[T]:
    try:
        return buffer_cache[fpath][identifier]
    except KeyError:
        return None

async def purge_buffers(fpath: str,
                             deleted_cache: TTLCache[str, Literal[True]],
                             *cache_list: FileBufferCache) -> None:
    deleted_cache.update({fpath:True})
    for cache in cache_list:
        buffered_mapping = cache.pop(fpath, {})
        for _, buffered_obj in buffered_mapping.items():
            await buffered_obj.close()

def rename_buffers(old_fpath: str, new_fpath: str,
                        *cache_list: FileBufferCache) -> None:
    for cache in cache_list:
        buffered_mapping: FileBufferCacheItem = cache.pop(old_fpath, {})
        cache[new_fpath] = buffered_mapping #type: ignore since buffered_mapping was popped from the same cache

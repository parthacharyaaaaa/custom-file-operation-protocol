'''Basic cache operations to support higher-level `FILE` request handlers and file operations'''

from cachetools import TTLCache
from aiofiles.threadpool.binary import AsyncBufferedReader
from aiofiles.threadpool.binary import AsyncBufferedIOBase, AsyncBufferedReader
from typing import Literal, Union

__all__ = ('remove_reader', 'get_reader', 'purge_file_entries', 'rename_file_entries')

def remove_reader(read_cache: TTLCache[str, dict[str, AsyncBufferedReader]], fpath: str, identifier: str) -> None:
    try:
        read_cache[fpath].pop(identifier, None)
    except KeyError:
        return None
    
def get_reader(read_cache: TTLCache[str, dict[str, AsyncBufferedReader]], fpath: str, identifier: str) -> AsyncBufferedReader:
    try:
        return read_cache[fpath][identifier]
    except KeyError:
        return None
    
async def purge_file_entries(fpath: str, deleted_cache: TTLCache[str, Literal[True]], *cache_list: TTLCache[str, dict[str, Union[AsyncBufferedIOBase, AsyncBufferedReader]]]) -> None:
    deleted_cache.update({fpath:True})
    for cache in cache_list:
        buffered_mapping = cache.pop(fpath, {})
        for _, buffered_obj in buffered_mapping.items():
            await buffered_obj.close()

def rename_file_entries(old_fpath: str, new_fpath: str, *cache_list: TTLCache[str, dict[str, Union[AsyncBufferedIOBase, AsyncBufferedReader]]]) -> None:
    for cache in cache_list:
        buffered_mapping = cache.pop(old_fpath, {})
        cache[new_fpath] = buffered_mapping

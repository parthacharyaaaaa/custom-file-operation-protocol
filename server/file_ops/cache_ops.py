from cachetools import TTLCache
from aiofiles.threadpool.binary import AsyncBufferedReader

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
from server.file_ops.cache_ops import remove_reader, get_reader
import aiofiles
from aiofiles.threadpool.binary import AsyncBufferedReader
from typing import Optional
from cachetools import TTLCache
import os

async def preemptive_eof_check(reader: AsyncBufferedReader) -> bool:
    if not await reader.read(1):
        return False
    await reader.seek(-1)
    return True

async def read_file(fpath: str, deleted_cache: TTLCache[str], read_cache: TTLCache[str, dict[str, AsyncBufferedReader]], cursor_position: int, nbytes: int = -1, reader_keepalive: bool = False, purge_reader: bool = False, identifier: Optional[str] = None, cached: bool = False) -> tuple[bytes, int, bool]:
    if deleted_cache.get(fpath) or not os.path.isfile(fpath):
        raise FileNotFoundError

    eof_reached: bool = False
    if cached:
        reader: AsyncBufferedReader = get_reader(read_cache, fpath, identifier)
        reader_found: bool = reader is not None

        if reader and await reader.tell() != cursor_position:   # Give priority to position received from client
            await reader.seek(cursor_position)
        if not reader:
            # Fallback to cursor_position
            reader: AsyncBufferedReader = await aiofiles.open(file=fpath, mode='rb')
            await reader.seek(cursor_position)

        # Reader is now ready
        data: bytes = await reader.read(nbytes)
        
        # Check EOF
        eof_reached = bool(data) and await preemptive_eof_check(reader)
        cursor_position = await reader.tell()

        if not (eof_reached or reader_found or purge_reader):
            # Cache new reader
            read_cache.setdefault(fpath, {})[identifier] = reader
        
        if purge_reader:
            await reader.close()
            remove_reader(read_cache, fpath, identifier)

        return data, cursor_position, eof_reached
    
    # Reader does not exist in cache
    reader: AsyncBufferedReader = await aiofiles.open(fpath, 'rb')
    try:
        data: bytes = await reader.read()
        cursor_position = await reader.tell()
        eof_reached = bool(data) and await preemptive_eof_check(reader)

        if reader_keepalive and not eof_reached:
            read_cache.setdefault(fpath, {})[identifier] = reader
    finally:
        if not reader_keepalive:
            await reader.close()

    return data, cursor_position, eof_reached
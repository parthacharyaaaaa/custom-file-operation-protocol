import asyncio
from server.file_ops.cache_ops import remove_reader, get_reader
import aiofiles
from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncBufferedIOBase
from typing import Optional, Union, Literal
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

async def write_file(fpath: str, data: Union[bytes, str], deleted_cache: TTLCache[str], write_cache: TTLCache[str, dict[str, AsyncBufferedIOBase]], cursor_position: int, writer_keepalive: bool = False, purge_writer: bool = False, identifier: Optional[str] = None, cached: bool = False) -> int:
    if deleted_cache.get(fpath) or not os.path.isfile(fpath):
        raise FileNotFoundError()
    
    # Only one coroutine is allowed to write to a file at a given time
    if cached:
        if not identifier: raise ValueError('Cached usage requires identifier for writer')
        writer: AsyncBufferedIOBase = get_reader(write_cache, fpath, identifier)
        writer_found: bool = writer is not None

        if not writer_found:
            writer: AsyncBufferedIOBase = await aiofiles.open(fpath, '+wb')

        if await writer.tell() != cursor_position:
            await writer.seek(cursor_position)

        # Writer is ready now
        await writer.write(data)

        if not (writer_found or purge_writer):
            write_cache.setdefault(fpath, {}).update({identifier:writer})
        
        if purge_writer:
            remove_reader(write_cache, fpath, identifier)
            await writer.close()
        
        return cursor_position + len(data)
        
    writer: AsyncBufferedReader = await aiofiles.open(fpath, mode='+wb')
    await writer.seek(cursor_position)
    try:
        await writer.write(data)
        if writer_keepalive:
            write_cache.setdefault(fpath, {}).update({identifier:writer})
    except IOError:
        await writer.close()
    finally:
        if not (writer_keepalive or writer.closed):
            await writer.close()
    
    return cursor_position + len(data)

async def append_file(fpath: str, data: Union[bytes, str], deleted_cache: TTLCache[str], append_cache: TTLCache[str, dict[str, AsyncBufferedIOBase]], append_writer_keepalive: bool = False, purge_append_writer: bool = False, identifier: Optional[str] = None, cached: bool = False) -> int:
    if deleted_cache.get(fpath) or not os.path.isfile(fpath):
        raise FileNotFoundError()
    
    # Only one coroutine is allowed to write to a file at a given time
    if cached:
        if not identifier: raise ValueError('Cached usage requires identifier for writer')
        append_writer: AsyncBufferedIOBase = get_reader(append_cache, fpath, identifier)
        append_writer_found: bool = append_writer is not None

        if not append_writer_found:
            append_writer: AsyncBufferedIOBase = await aiofiles.open(fpath, '+ab')

        # Writer is ready now
        await append_writer.write(data)

        if not (append_writer_found or purge_append_writer):
            append_cache.setdefault(fpath, {}).update({identifier:append_writer})
        
        if purge_append_writer:
            remove_reader(append_cache, fpath, identifier)
            await append_writer.close()
        
        return len(data)
        
    append_writer: AsyncBufferedReader = await aiofiles.open(fpath, mode='+qb')
    try:
        await append_writer.write(data)
        if append_writer_keepalive:
            append_cache.setdefault(fpath, {}).update({identifier:append_writer})
    except IOError:
        await append_writer.close()
    finally:
        if not (append_writer_keepalive or append_writer.closed):
            await append_writer.close()
    
    return len(data)

async def create_file(owner: str, filename: str, root: os.PathLike, extension: str = '.txt') -> Optional[str]:
    parent_dir: os.PathLike = os.path.join(root, owner.lower())
    os.makedirs(parent_dir, exist_ok=True)

    fpath: os.PathLike = os.path.join(parent_dir, f'{filename}{extension}')
    try:
        async with aiofiles.open(fpath, mode='x'): pass
    except FileExistsError:
        return None
    
    return fpath

def delete_file(fpath: os.PathLike, deleted_cache: TTLCache[str, Literal[True]]) -> bool:
    if fpath in deleted_cache or not os.path.isfile(fpath):
        raise False
    
    try:
        os.remove(fpath)
        return True
    except (FileNotFoundError, PermissionError, OSError):
        return False

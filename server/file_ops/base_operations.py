import os
import shutil
from uuid import uuid4
from typing import Optional, Union, Literal
from zlib import adler32
from math import inf

import asyncio
import aiofiles
from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncBufferedIOBase
from cachetools import TTLCache

from server.bootup import file_locks
from server.config.server_config import SERVER_CONFIG
from server.errors import FileNotFound, InternalServerError
from server.file_ops.cache_ops import remove_reader, get_reader, purge_file_entries, rename_file_entries


async def acquire_file_lock(filename: str, requestor: str, ttl: Optional[int] = None, max_attempts: Optional[int] = inf) -> Literal[True]:
    '''Indefinitely start a coroutine to wait for a lock on a file to be acquired. It is best to use this with `asyncio.wait_for` to prevent the caller from being stalled indefinitely.  
    '''
    
    global file_locks
    ttl = min(SERVER_CONFIG.file_lock_ttl, (ttl or SERVER_CONFIG.file_lock_ttl))
    holder_checksum = adler32(requestor.encode('utf-8'))
    attempt: int = 0

    while attempt < max_attempts:
        lock_checksum = file_locks.setdefault(filename, holder_checksum)
        if not lock_checksum:
            raise FileNotFound(f'File {filename} deleted') 
        if lock_checksum == holder_checksum:
            return True
        attempt += 1
        asyncio.sleep(0.1)

async def preemptive_eof_check(reader: AsyncBufferedReader) -> bool:
    if not await reader.read(1):
        return False
    await reader.seek(-1)
    return True

async def read_file(root: os.PathLike, fpath: str, deleted_cache: TTLCache[str], read_cache: TTLCache[str, dict[str, AsyncBufferedReader]], cursor_position: int, nbytes: int = -1, reader_keepalive: bool = False, purge_reader: bool = False, identifier: Optional[str] = None, cached: bool = False) -> tuple[bytes, int, bool]:
    abs_fpath: os.PathLike = os.path.join(root, fpath)
    if deleted_cache.get(fpath) or not os.path.isfile(abs_fpath):
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

async def write_file(root: os.PathLike, fpath: str, data: Union[bytes, str], deleted_cache: TTLCache[str], write_cache: TTLCache[str, dict[str, AsyncBufferedIOBase]], cursor_position: int, writer_keepalive: bool = False, purge_writer: bool = False, identifier: Optional[str] = None, cached: bool = False) -> int:
    abs_fpath: os.PathLike = os.path.join(root, fpath)
    if deleted_cache.get(fpath) or not os.path.isfile(abs_fpath):
        raise FileNotFoundError()
    
    # Only one coroutine is allowed to write to a file at a given time
    if cached:
        if not identifier: raise ValueError('Cached usage requires identifier for writer')
        writer: AsyncBufferedIOBase = get_reader(write_cache, fpath, identifier)
        writer_found: bool = writer is not None

        if not writer_found:
            writer: AsyncBufferedIOBase = await aiofiles.open(abs_fpath, '+wb')

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

async def append_file(root: os.PathLike, fpath: str, data: Union[bytes, str], deleted_cache: TTLCache[str], append_cache: TTLCache[str, dict[str, AsyncBufferedIOBase]], append_writer_keepalive: bool = False, purge_append_writer: bool = False, identifier: Optional[str] = None, cached: bool = False) -> int:
    abs_fpath: os.PathLike = os.path.join(root, fpath)
    if deleted_cache.get(fpath) or not os.path.isfile(abs_fpath):
        raise FileNotFoundError()
    
    # Only one coroutine is allowed to write to a file at a given time
    if cached:
        if not identifier: raise ValueError('Cached usage requires identifier for writer')
        append_writer: AsyncBufferedIOBase = get_reader(append_cache, fpath, identifier)
        append_writer_found: bool = append_writer is not None

        if not append_writer_found:
            append_writer: AsyncBufferedIOBase = await aiofiles.open(abs_fpath, '+ab')

        # Writer is ready now
        await append_writer.write(data)
        cursor: int = await append_writer.tell()
        if not (append_writer_found or purge_append_writer):
            append_cache.setdefault(fpath, {}).update({identifier:append_writer})
        
        if purge_append_writer:
            remove_reader(append_cache, fpath, identifier)
            await append_writer.close()
        
        return cursor
        
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

async def create_file(root: os.PathLike, owner: str, filename: str) -> tuple[Optional[str], Optional[float]]:
    owner = owner.lower()
    parent_dir: os.PathLike = os.path.join(root, owner)
    os.makedirs(parent_dir, exist_ok=True)

    fpath: os.PathLike = os.path.join(parent_dir, filename)
    try:
        async with aiofiles.open(fpath, mode='x'): ...
        return os.path.join(owner, filename), os.path.getctime(fpath)

    except FileExistsError:
        return None, None
    

async def delete_file(root: os.PathLike, fpath: os.PathLike, deleted_cache: TTLCache[str, Literal[True]], *caches: TTLCache[str, dict[str, Union[AsyncBufferedIOBase, AsyncBufferedReader]]]) -> bool:
    abs_fpath: os.PathLike = os.path.join(root, fpath)
    if fpath in deleted_cache or not os.path.isfile(abs_fpath):
        raise False
    try:
        os.remove(abs_fpath)
        await purge_file_entries(fpath, deleted_cache, *caches)
        return True
    except (FileNotFoundError, PermissionError, OSError):
        return False

def rename_file(root: os.PathLike, fpath: os.PathLike, name: str, deleted_cache: TTLCache[str, Literal[True]], *caches: TTLCache[str, dict[str, Union[AsyncBufferedReader, AsyncBufferedIOBase]]]) -> bool:
    abs_fpath: os.PathLike = os.path.join(root, fpath)
    if fpath in deleted_cache or not os.path.isfile(abs_fpath):
        return False
    
    try:
        new_fpath: os.PathLike = os.path.join(os.path.dirname(abs_fpath), name)
        os.rename(fpath, new_fpath)
        rename_file_entries(fpath, new_fpath, *caches)
        
        return True
    except (PermissionError, OSError):
        return False
    
def transfer_file(root: os.PathLike, previous_owner: str, file: os.PathLike, new_owner: os.PathLike, deleted_cache: TTLCache[str, Literal[True]],
                  new_name: Optional[str] = None, **cache_mapping) -> os.PathLike:
    prev_fpath = os.path.join(root, previous_owner, file)
    if prev_fpath in deleted_cache or not os.path.isfile(prev_fpath):
        return None

    try:
        if not os.path.isdir(root):
            os.makedirs(root, exist_ok=True)

        if new_name:
            file = new_name
        new_fpath: os.PathLike = os.path.join(root, new_owner, file)
        if os.path.isfile(new_fpath):
            file = '_'.join(uuid4().hex, file)
            new_fpath = os.path.join(root, new_owner, file)
        
        os.replace(src=prev_fpath, dst=new_fpath)
        return file
    except (PermissionError, OSError):
        return None

def delete_directory(root: os.PathLike, dirname: str) -> list[str]:
    abs_dpath: os.PathLike = os.path.join(root, dirname)
    walk_gen = os.walk(top=abs_dpath)
    try:
        shutil.rmtree(os.path.join(root, dirname))
        return next(walk_gen)[2]
    except (OSError, PermissionError):
        raise InternalServerError
    
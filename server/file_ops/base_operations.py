'''Basic file I/O operations to support higher-level `FILE` request handlers'''

import os
import shutil
from uuid import uuid4
from typing import Optional, Union, Literal, Final

import asyncio
import aiofiles
from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncBufferedIOBase
from cachetools import TTLCache

from server import errors
from server.file_ops.cache_ops import remove_reader, get_reader, purge_file_entries, rename_file_entries
from server.file_ops.typing import FileBuffer

__all__ = ('acquire_file_lock',
           'preemptive_eof_check',
           'read_file',
           'write_file',
           'append_file',
           'create_file',
           'delete_file',
           'rename_file',
           'transfer_file',
           'delete_directory')

async def acquire_file_lock(file_locks: TTLCache[str, str],
                            filename: str,
                            requestor: str,
                            max_attempts: int = 10000) -> Optional[Literal[True]]:
    '''Indefinitely start a coroutine to wait for a lock on a file to be acquired. It is best to use this with `asyncio.wait_for` to prevent the caller from being stalled indefinitely.'''
    attempt: int = 0
    while attempt < max_attempts:
        file_lock_holder = file_locks.setdefault(filename, requestor)
        if file_lock_holder == requestor:
            return True
        attempt += 1
        await asyncio.sleep(0.1)

async def preemptive_eof_check(reader: AsyncBufferedReader) -> bool:
    if not await reader.read(1):
        return False
    await reader.seek(await reader.tell() - 1)
    return True

async def read_file(root: os.PathLike, fpath: str, identifier: str,
                    deleted_cache: TTLCache[str, str], read_cache: TTLCache[str, dict[str, AsyncBufferedReader]],
                    cursor_position: int, nbytes: int = -1,
                    reader_keepalive: bool = False, purge_reader: bool = False) -> tuple[bytes, int, bool]:
    abs_fpath: Final[str] = os.path.join(root, fpath)
    if deleted_cache.get(fpath) or not os.path.isfile(abs_fpath):
        raise FileNotFoundError

    eof_reached: bool = False
    reader = get_reader(read_cache, fpath, identifier)
    if not reader:
        reader = await aiofiles.open(file=abs_fpath, mode='rb')
    
    if not await reader.tell() == cursor_position:
        await reader.seek(cursor_position)

    # File reader prepped
    read_data: bytes = await reader.read(nbytes)
        
    # Check EOF
    eof_reached = not await preemptive_eof_check(reader)
    cursor_position = await reader.tell()

    if purge_reader:
        await reader.close()
        remove_reader(read_cache, fpath, identifier)
    elif reader_keepalive:
        read_cache.setdefault(fpath, {})[identifier] = reader

    return read_data, cursor_position, eof_reached

async def write_file(root: os.PathLike, fpath: str, data: bytes,
                     identifier: str,
                     deleted_cache: TTLCache[str, str], amendment_cache: TTLCache[str, dict[str, AsyncBufferedIOBase]],
                     cursor_position: int, trunacate: bool = False,
                     writer_keepalive: bool = False, purge_writer: bool = False) -> int:
    abs_fpath: str = os.path.join(root, fpath)
    if deleted_cache.get(fpath) or not os.path.isfile(abs_fpath):
        raise FileNotFoundError()
    
    writer = get_reader(amendment_cache, fpath, identifier)
    if not writer:
        writer = await aiofiles.open(abs_fpath, 'wb' if trunacate else 'r+b')

    if await writer.tell() != cursor_position:
        await writer.seek(cursor_position)

    new_position: int = await writer.tell() + len(data)
    try:
        await writer.write(data)
        if purge_writer:
            remove_reader(amendment_cache, fpath, identifier)
            await writer.close()
        elif writer_keepalive:
            amendment_cache.setdefault(fpath, {}).update({identifier:writer})
    except IOError:
        remove_reader(amendment_cache, fpath, identifier)
        await writer.close()
        raise IOError
    
    return new_position

async def append_file(root: os.PathLike, fpath: str,
                      data: bytes,
                      identifier: str,
                      deleted_cache: TTLCache[str, str], amendment_cache: TTLCache[str, dict[str, AsyncBufferedIOBase]],
                      append_writer_keepalive: bool = False, purge_append_writer: bool = False, writer_cached: bool = False) -> int:
    abs_fpath: str = os.path.join(root, fpath)
    if deleted_cache.get(fpath) or not os.path.isfile(abs_fpath):
        raise FileNotFoundError()
    
    # Only one coroutine is allowed to write to a file at a given time
    append_writer: Optional[AsyncBufferedIOBase] = None
    if writer_cached:
        if not identifier: raise ValueError('Cached usage requires identifier for writer')
        append_writer = get_reader(amendment_cache, fpath, identifier)

        if not append_writer:
            append_writer = await aiofiles.open(abs_fpath, '+ab')
        
    append_writer = await aiofiles.open(abs_fpath, mode='+ab')
    try:
        await append_writer.write(data)
    except IOError:
        remove_reader(amendment_cache, fpath, identifier)
        await append_writer.close()
        return -1
    if append_writer_keepalive and not writer_cached:
        amendment_cache.setdefault(fpath, {}).update({identifier:append_writer})
    elif purge_append_writer:
        remove_reader(amendment_cache, fpath, identifier)
    
    return len(data)

async def create_file(root: os.PathLike, owner: str, filename: str) -> tuple[Optional[str], Optional[float]]:
    owner = owner.lower()
    parent_dir: str = os.path.join(root, owner)
    os.makedirs(parent_dir, exist_ok=True)

    fpath: str = os.path.join(parent_dir, filename)
    try:
        async with aiofiles.open(fpath, mode='x'): ...
        return os.path.join(owner, filename), os.path.getctime(fpath)

    except FileExistsError:
        return None, None

async def delete_file(root: os.PathLike, fpath: str,
                      deleted_cache: TTLCache[str, Literal[True]],
                      *caches: TTLCache[str, dict[str, Union[AsyncBufferedIOBase, AsyncBufferedReader]]]) -> bool:
    abs_fpath: Final[str] = os.path.join(root, fpath)
    if fpath in deleted_cache or not os.path.isfile(abs_fpath):
        return False
    try:
        os.remove(abs_fpath)
        await purge_file_entries(fpath, deleted_cache, *caches)
        return True
    except (FileNotFoundError, PermissionError, OSError):
        return False

def rename_file(root: os.PathLike, fpath: str, name: str,
                deleted_cache: TTLCache[str, Literal[True]],
                *caches: TTLCache[str, dict[str, Union[AsyncBufferedReader, AsyncBufferedIOBase]]]) -> bool:
    abs_fpath: Final[str] = os.path.join(root, fpath)
    if fpath in deleted_cache or not os.path.isfile(abs_fpath):
        return False
    
    try:
        new_fpath: str = os.path.join(os.path.dirname(abs_fpath), name)
        os.rename(fpath, new_fpath)
        rename_file_entries(fpath, new_fpath, *caches)
        
        return True
    except (PermissionError, OSError):
        return False
    
def transfer_file(root: os.PathLike,
                  previous_owner: str, file: str, new_owner: str,
                  deleted_cache: TTLCache[str, Literal[True]],
                  new_name: Optional[str] = None) -> Optional[str]:
    prev_fpath: str = os.path.join(root, previous_owner, file)
    if prev_fpath in deleted_cache or not os.path.isfile(prev_fpath):
        return None

    try:
        if not os.path.isdir(root):
            os.makedirs(root, exist_ok=True)

        if new_name:
            file = new_name
        new_fpath: str = os.path.join(root, new_owner, file)
        if os.path.isfile(new_fpath):
            file = '_'.join((uuid4().hex, file))
            new_fpath = os.path.join(root, new_owner, file)
        
        os.replace(src=prev_fpath, dst=new_fpath)
        return file
    except (PermissionError, OSError):
        return None

def delete_directory(root: os.PathLike, dirname: str, raise_on_absence: bool = False) -> list[str]:
    abs_dpath: Final[str] = os.path.join(root, dirname)
    if not os.path.isdir(abs_dpath) and raise_on_absence:
        raise FileNotFoundError(f"{abs_dpath} doesn't exist")
    
    try:
        deleted_files = next(os.walk(top=abs_dpath))[2]
        shutil.rmtree(abs_dpath)
        return deleted_files
    except (OSError, PermissionError):
        raise errors.InternalServerError

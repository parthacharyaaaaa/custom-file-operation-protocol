import sys
import aiofiles
import itertools
import asyncio
from typing import Sequence, Union

async def display(*args: Union[str, bytes], sep=b' ', end=b'\n'):
    write_buffer: bytes = sep.join(arg.encode('utf-8') if isinstance(arg, str) else arg for arg in args)
    async with aiofiles.open(sys.stdout.fileno(), mode='wb') as stdout:
        await stdout.write(write_buffer)
        await stdout.write(end)

async def display_spinner(sequence: Sequence[bytes] = [b'|', b'/', b'-', b'\\'], interval: float = 0.075):
    cycle = itertools.cycle(sequence)
    async with aiofiles.open(sys.stdout.fileno(), mode='wb') as stdout:
        for char in cycle:
            await stdout.write(char)
            await stdout.flush()
            await stdout.write(b'\r')
            await asyncio.sleep(interval)

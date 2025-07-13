import sys
import aiofiles

async def display(*args, sep=b' ', end=b'\n'):
    write_buffer: bytes = sep.join(bytes(arg) for arg in args)
    async with aiofiles.open(sys.stdout.fileno(), mode='wb') as stdout:
        await stdout.write(write_buffer)
        await stdout.write(end)
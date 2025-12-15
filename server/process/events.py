import asyncio
import os
from typing import Final

__all__ = ('SHUTDOWN_EVENT',
           'LOG_CLEANUP_EVENT',
           'CACHE_CLEANUP_EVENT',
           'CLEANUP_WAITING_PERIOD')

# Global event to signal server shutdonw
SHUTDOWN_EVENT: Final[asyncio.Event] = asyncio.Event()

# Flags for specific background tasks
LOG_CLEANUP_EVENT: Final[asyncio.Event] = asyncio.Event()
CACHE_CLEANUP_EVENT: Final[asyncio.Event] = asyncio.Event()

CLEANUP_WAITING_PERIOD: Final[int] = int(os.environ["CLEANUP_WAITING_PERIOD"])
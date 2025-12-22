import asyncio
import os
import weakref
from typing import Any, Final

__all__ = ('SHUTDOWN_EVENT',
           'LOG_CLEANUP_EVENT',
           'CACHE_CLEANUP_EVENT',
           'CONNECTION_POOL_CLEANUP_EVENT',
           'AUTH_STATE_CLEANUP_EVENT',
           'CLEANUP_WAITING_PERIOD',
           'EventProxy',
           'ExclusiveEventProxy')

# Global event to signal server shutdonw
SHUTDOWN_EVENT: Final[asyncio.Event] = asyncio.Event()

# Flags for specific background tasks
LOG_CLEANUP_EVENT: Final[asyncio.Event] = asyncio.Event()
CACHE_CLEANUP_EVENT: Final[asyncio.Event] = asyncio.Event()
AUTH_STATE_CLEANUP_EVENT: Final[asyncio.Event] = asyncio.Event()
CONNECTION_POOL_CLEANUP_EVENT: Final[asyncio.Event] = asyncio.Event()

CLEANUP_WAITING_PERIOD: Final[int] = int(os.environ["CLEANUP_WAITING_PERIOD"])

class EventProxy:
    '''Read-only proxy to expose an asyncio.Event'''
    __slots__ = ('_event')

    def __init__(self, event: asyncio.Event) -> None:
        self._event: Final[asyncio.Event] = event
    
    async def wait(self) -> None:
        await self._event.wait()

    def is_set(self) -> bool:
        return self._event.is_set()
    
class ExclusiveEventProxy(EventProxy):
    '''
    Mutable proxy to allow only a single object to set/reset an asyncio.Event
    '''
    __slots__ = ('_holder')

    def __init__(self, event: asyncio.Event, holder: weakref.ReferenceType[Any]) -> None:
        self._holder = holder
        super().__init__(event)

    def set(self, caller: Any) -> None:
        if (identity:=id(caller)) != self._holder:
            raise ValueError(f"Holder at <f{identity}> does not have permission to set event")
        self._event.set()

    def clear(self, caller: Any) -> None:
        if (identity:=id(caller)) != self._holder:
            raise ValueError(f"Holder at <f{identity}> does not have permission to set event")
        self._event.clear()

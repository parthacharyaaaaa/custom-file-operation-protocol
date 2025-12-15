'''Helper data structures for server functionality'''
import asyncio
from typing import Final

__all__ = ('EventProxy',)

class EventProxy:
    __slots__ = ('_event')

    def __init__(self, event: asyncio.Event) -> None:
        self._event: Final[asyncio.Event] = event
    
    async def wait(self) -> None:
        await self._event.wait()

    def is_set(self) -> bool:
        return self._event.is_set()
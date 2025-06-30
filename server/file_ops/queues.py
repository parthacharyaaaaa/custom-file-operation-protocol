import asyncio

LOW_PRIORITY_QUEUE: asyncio.Queue = asyncio.Queue()
LOW_PRIORITY_QUEUE_LOCK: asyncio.Lock = asyncio.Lock()

MID_PRIORITY_QUEUE: asyncio.Queue = asyncio.Queue()
MID_PRIORITY_QUEUE_LOCK: asyncio.Lock = asyncio.Lock()

HIGH_PRIORITY_QUEUE: asyncio.Queue = asyncio.Queue()
HIGH_PRIORITY_QUEUE_LOCK: asyncio.Lock = asyncio.Lock()
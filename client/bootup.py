import asyncio
from session_manager import SessionManager


session_manager: SessionManager = None
stream_lock: asyncio.Lock = asyncio.Lock()
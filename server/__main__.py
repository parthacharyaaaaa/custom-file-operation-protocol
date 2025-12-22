'''Entrypoint script for running the server'''

import asyncio
import sys
from typing import Final

from server.process.events import SHUTDOWN_EVENT, SHUTDOWN_CHECKPOINT_EVENTS
from server.process.control import serve, system_exit

def main() -> None:
    if sys.platform == 'win32':     # psycopg3 not compatible with asyncio.WindowsProactorEventLoopPolicy (default loop for Windows)
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    loop: Final[asyncio.AbstractEventLoop] = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(serve())
    except BaseException:
        SHUTDOWN_EVENT.set()
        try:
            print("Beginning system exit...")
            loop.run_until_complete(system_exit(*SHUTDOWN_CHECKPOINT_EVENTS))
            print("Ended system exit...")
        except Exception:
            pass

        raise
    finally:
        loop.close()

if __name__ == '__main__':
    main()
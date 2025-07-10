import asyncio
import os
import sys

from server.bootup import init_connection_master, init_user_master, init_file_lock, init_logger, init_caches
from server.config.server_config import SERVER_CONFIG
from psycopg.conninfo import make_conninfo

async def main() -> None:
    await init_connection_master(conninfo=make_conninfo(user=os.environ['PG_USERNAME'], password=os.environ['PG_PASSWORD'], host=os.environ['PG_HOST'], port=os.environ['PG_PORT'], dbname=os.environ['PG_DBNAME']))
    init_user_master()
    init_file_lock()
    init_caches()
    init_logger()
    from server.callback import callback    # TEMPFIX: Imports callback after all global singletons are initialized to avoid referencing None at runtime

    server: asyncio.Server = await asyncio.start_server(client_connected_cb=callback,
                                                        host=str(SERVER_CONFIG.host), port=SERVER_CONFIG.port)
    async with server:
        await server.serve_forever()

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
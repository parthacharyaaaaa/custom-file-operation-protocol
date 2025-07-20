import asyncio
from functools import partial
import os
import sys

from psycopg.conninfo import make_conninfo

from server.authz.user_manager import UserManager
from server.bootup import create_server_config, create_connection_master, create_log_queue, create_user_master, create_caches, create_file_lock, start_logger
from server.callback import callback
from server.config.server_config import ServerConfig
from server.connectionpool import ConnectionPoolManager
from server.dependencies import ServerSingletonsRegistry, NT_GLOBAL_FILE_LOCK, NT_GLOBAL_LOG_QUEUE

async def main() -> None:
    # Initialize all global singletons
    SERVER_CONFIG: ServerConfig = create_server_config()
    CONNECTION_MASTER: ConnectionPoolManager = await create_connection_master(conninfo=make_conninfo(user=os.environ['PG_USERNAME'],
                                                                                                     password=os.environ['PG_PASSWORD'],
                                                                                                     host=os.environ['PG_HOST'],
                                                                                                     port=os.environ['PG_PORT'],
                                                                                                     dbname=os.environ['PG_DBNAME']),
                                                                              config=SERVER_CONFIG)
    
    LOG_QUEUE: NT_GLOBAL_LOG_QUEUE = create_log_queue()
    
    USER_MASTER: UserManager = create_user_master(connection_master=CONNECTION_MASTER,
                                                  config=SERVER_CONFIG,
                                                  log_queue=LOG_QUEUE)
    
    FILE_LOCK: NT_GLOBAL_FILE_LOCK =  create_file_lock(config=SERVER_CONFIG)
   
    READ_CACHE, AMENDMENT_CACHE, DELETION_CACHE = create_caches(config=SERVER_CONFIG)

    SERVER_DEPENDENCY_REGISTRY: ServerSingletonsRegistry = ServerSingletonsRegistry(server_config=SERVER_CONFIG,
                                                                                    user_manager=USER_MASTER,
                                                                                    connection_pool_manager=CONNECTION_MASTER,
                                                                                    log_queue=LOG_QUEUE,
                                                                                    reader_cache=READ_CACHE,
                                                                                    amendment_cache=AMENDMENT_CACHE,
                                                                                    deletion_cache=DELETION_CACHE,
                                                                                    file_locks=FILE_LOCK)

    start_logger(log_queue=LOG_QUEUE, config=SERVER_CONFIG, connection_master=CONNECTION_MASTER)

    server: asyncio.Server = await asyncio.start_server(client_connected_cb=partial(callback, SERVER_DEPENDENCY_REGISTRY),
                                                        host=str(SERVER_CONFIG.host), port=SERVER_CONFIG.port)
    async with server:
        await server.serve_forever()

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
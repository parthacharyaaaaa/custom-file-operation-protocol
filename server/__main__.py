'''Entrypoint script for running the server'''

import asyncio
import os
import sys
from typing import Final
from types import MappingProxyType

from cachetools import TTLCache

from psycopg.conninfo import make_conninfo

from models.flags import CategoryFlag

from server.authz.user_manager import UserManager
from server.bootup import (create_server_config, create_connection_master,
                           create_log_queue, create_user_master,
                           create_caches, create_file_lock, create_storage_cache,
                           start_logger, start_server, partialise_request_subhandlers)

from server.config.server_config import ServerConfig
from server.database.connections import ConnectionPoolManager
from server.datastructures import EventProxy
from server.dependencies import ServerSingletonsRegistry
from server.dispatch import (TOP_LEVEL_REQUEST_MAPPING, auth_subhandler_mapping,
                             file_subhandler_mapping, info_subhandler_mapping, permission_subhandler_mapping)

from server.logging import ActivityLog
from server.tls import credentials
from server.typing import PartialisedRequestHandler

async def main() -> None:
    # Initialize all global singletons
    shutdown_event: Final[asyncio.Event] = asyncio.Event()
    event_proxy: Final[EventProxy] = EventProxy(shutdown_event)

    server_config: Final[ServerConfig] = create_server_config()
    connection_master: Final[ConnectionPoolManager] = await create_connection_master(conninfo=make_conninfo(user=os.environ['PG_USERNAME'],
                                                                                                            password=os.environ['PG_PASSWORD'],
                                                                                                            host=os.environ['PG_HOST'],
                                                                                                            port=os.environ['PG_PORT'],
                                                                                                            dbname=os.environ['PG_DBNAME']),
                                                                                    config=server_config)
    
    log_queue: Final[asyncio.Queue[ActivityLog]] = create_log_queue(server_config)
    
    user_master: Final[UserManager] = create_user_master(connection_master=connection_master,
                                                         config=server_config,
                                                         log_queue=log_queue)
    
    file_lock: Final[TTLCache[str, bytes]] = create_file_lock(config=server_config)
   
    read_cache, amendment_cache, deletion_cache = create_caches(config=server_config)
    storage_cache = create_storage_cache(connection_master, server_config, event_proxy)

    server_dependency_registry: Final[ServerSingletonsRegistry] = ServerSingletonsRegistry(server_config=server_config,
                                                                                           user_manager=user_master,
                                                                                           connection_pool_manager=connection_master,
                                                                                           log_queue=log_queue,
                                                                                           reader_cache=read_cache,
                                                                                           amendment_cache=amendment_cache,
                                                                                           deletion_cache=deletion_cache,
                                                                                           file_locks=file_lock,
                                                                                           storage_cache=storage_cache)

    start_logger(log_queue=log_queue, config=server_config, connection_master=connection_master, shutdown_event=event_proxy)

    # Initially generate certificates if not present
    if not (server_config.key_filepath.is_file() and server_config.certificate_filepath.is_file()):
        credentials.generate_self_signed_credentials(dns_name=str(server_config.host),
                                                     cert_filepath=server_config.certificate_filepath,
                                                     key_filepath=server_config.key_filepath)

    # Inject singletons into request subhandler coroutines
    routing_map: Final[MappingProxyType[CategoryFlag, PartialisedRequestHandler]] = partialise_request_subhandlers(
        singleton_registry=server_dependency_registry,
        top_handler_mapping=TOP_LEVEL_REQUEST_MAPPING,
        subhandler_mappings=[auth_subhandler_mapping, info_subhandler_mapping, permission_subhandler_mapping, file_subhandler_mapping])

    reference_time: float = os.stat(server_config.certificate_filepath, follow_symlinks=False).st_mtime
    while True:
        running_server: asyncio.Task = asyncio.create_task(start_server(dependency_registry=server_dependency_registry, request_handler_map=routing_map))
        while not running_server.done():
            await asyncio.sleep(server_config.rollover_check_poll_interval)
            modification_time: float = os.stat(server_config.certificate_filepath, follow_symlinks=False).st_mtime
            if modification_time != reference_time:
                reference_time = modification_time
                running_server.cancel()
                break


if sys.platform == 'win32':     # psycopg3 not compatible with asyncio.WindowsProactorEventLoopPolicy (default loop for Windows)
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
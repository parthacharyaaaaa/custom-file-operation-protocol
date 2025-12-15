import asyncio
import os
from types import MappingProxyType
from typing import Final

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
from server.process.events import SHUTDOWN_EVENT, CACHE_CLEANUP_EVENT, LOG_CLEANUP_EVENT
from server.tls import credentials
from server.typing import PartialisedRequestHandler

__all__ = ('system_exit',
           'serve')

async def system_exit() -> None:
    SHUTDOWN_EVENT.set()
    try:
        await asyncio.wait_for(asyncio.gather(LOG_CLEANUP_EVENT.wait(), CACHE_CLEANUP_EVENT.wait()),
                               CLEANUP_WAITING_PERIOD)
    except asyncio.TimeoutError:
        pass

async def serve() -> None:
    # Initialize all global singletons
    shutdown_event_proxy: Final[EventProxy] = EventProxy(SHUTDOWN_EVENT)
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
                                                         log_queue=log_queue,
                                                         shutdown_event=shutdown_event_proxy)
    
    file_lock: Final[TTLCache[str, bytes]] = create_file_lock(config=server_config)
   
    read_cache, amendment_cache, deletion_cache = create_caches(config=server_config)
    storage_cache = create_storage_cache(connection_master, server_config, shutdown_event_proxy, CACHE_CLEANUP_EVENT)

    server_dependency_registry: Final[ServerSingletonsRegistry] = ServerSingletonsRegistry(server_config=server_config,
                                                                                           user_manager=user_master,
                                                                                           connection_pool_manager=connection_master,
                                                                                           log_queue=log_queue,
                                                                                           reader_cache=read_cache,
                                                                                           amendment_cache=amendment_cache,
                                                                                           deletion_cache=deletion_cache,
                                                                                           file_locks=file_lock,
                                                                                           storage_cache=storage_cache)

    start_logger(log_queue=log_queue, config=server_config, connection_master=connection_master,
                 shutdown_event=shutdown_event_proxy, cleanup_event=LOG_CLEANUP_EVENT)

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
    while not SHUTDOWN_EVENT.is_set():
        server_task: asyncio.Task = asyncio.create_task(start_server(dependency_registry=server_dependency_registry,
                                                                     request_handler_map=routing_map))
        while not server_task.done() and not SHUTDOWN_EVENT.is_set():
            await asyncio.sleep(server_config.rollover_check_poll_interval)

            modification_time: float = os.stat(server_config.certificate_filepath, follow_symlinks=False).st_mtime
            if modification_time != reference_time:
                # Close current listener socket, and break out of server_task loop to restart server with new credentials
                reference_time = modification_time
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass
                break
        if SHUTDOWN_EVENT.is_set() and not server_task.done():
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

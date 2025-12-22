import asyncio
import os
from types import MappingProxyType
from typing import Final

from cachetools import TTLCache

from psycopg.conninfo import make_conninfo

from models.flags import CategoryFlag

from server.authz.user_manager import UserManager
from server.bootup import (create_server_config, create_connection_master,
                           create_logger, create_user_master,
                           create_caches, create_file_lock, create_storage_cache,
                           start_server, partialise_request_subhandlers)

from server.config.server_config import ServerConfig
from server.database.connections import ConnectionPoolManager
from server.dependencies import ServerSingletonsRegistry
from server.dispatch import (TOP_LEVEL_REQUEST_MAPPING, auth_subhandler_mapping,
                             file_subhandler_mapping, info_subhandler_mapping, permission_subhandler_mapping)

from server.logging import ActivityLog, Logger
from server.process.events import (SHUTDOWN_EVENT, CACHE_CLEANUP_EVENT, LOG_CLEANUP_EVENT,
                                   AUTH_STATE_CLEANUP_EVENT, CONNECTION_POOL_CLEANUP_EVENT,
                                   CLEANUP_WAITING_PERIOD, SHUTDOWN_POLLING_INTERVAL,
                                   EventProxy)
from server.tls import credentials
from server.typing import PartialisedRequestHandler

__all__ = ('system_exit',
           'serve')

async def system_exit(*shutdown_events: asyncio.Event) -> str:
    SHUTDOWN_EVENT.set()
    try:
        await asyncio.wait_for(asyncio.gather(shutdown_event.wait for shutdown_event in shutdown_events),
                               CLEANUP_WAITING_PERIOD)
        return "All shutdown tasks completed"
    except asyncio.TimeoutError:
        remaining_task_repr: tuple[str, ...] = tuple(repr(event) for event in shutdown_events if event.is_set())
        return f"Shutdown tasks timed out: {', '.join(remaining_task_repr)}"

async def serve() -> None:
    # Initialize all global singletons
    shutdown_event_proxy: Final[EventProxy] = EventProxy(SHUTDOWN_EVENT)
    server_config: Final[ServerConfig] = create_server_config()
    connection_master: Final[ConnectionPoolManager] = await create_connection_master(conninfo=make_conninfo(user=os.environ['PG_USERNAME'],
                                                                                                            password=os.environ['PG_PASSWORD'],
                                                                                                            host=os.environ['PG_HOST'],
                                                                                                            port=os.environ['PG_PORT'],
                                                                                                            dbname=os.environ['PG_DBNAME']),
                                                                                    config=server_config,
                                                                                    shutdown_poll_interval=SHUTDOWN_POLLING_INTERVAL,
                                                                                    shutdown_event=shutdown_event_proxy,
                                                                                    cleanup_event=CONNECTION_POOL_CLEANUP_EVENT)
    
    logger: Final[Logger] = create_logger(server_config, connection_master, SHUTDOWN_POLLING_INTERVAL, shutdown_event_proxy, LOG_CLEANUP_EVENT)
    
    user_master: Final[UserManager] = create_user_master(connection_master=connection_master,
                                                         config=server_config,
                                                         logger=logger,
                                                         shutdown_event=shutdown_event_proxy,
                                                         cleanup_event=AUTH_STATE_CLEANUP_EVENT,
                                                         shutdown_poll_interval=SHUTDOWN_POLLING_INTERVAL)
    
    file_lock: Final[TTLCache[str, bytes]] = create_file_lock(config=server_config)
   
    read_cache, amendment_cache, deletion_cache = create_caches(config=server_config)
    storage_cache = create_storage_cache(connection_master, server_config, SHUTDOWN_POLLING_INTERVAL, shutdown_event_proxy, CACHE_CLEANUP_EVENT)

    server_dependency_registry: Final[ServerSingletonsRegistry] = ServerSingletonsRegistry(server_config=server_config,
                                                                                           user_manager=user_master,
                                                                                           connection_pool_manager=connection_master,
                                                                                           logger=logger,
                                                                                           reader_cache=read_cache,
                                                                                           amendment_cache=amendment_cache,
                                                                                           deletion_cache=deletion_cache,
                                                                                           file_locks=file_lock,
                                                                                           storage_cache=storage_cache)

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
    # Outer loop to check for SHUTDOWN_EVENT
    while not SHUTDOWN_EVENT.is_set():
        server_task: asyncio.Task = asyncio.create_task(start_server(dependency_registry=server_dependency_registry,
                                                                     request_handler_map=routing_map))
        # Inner loop to restart server in case of certificate updation
        while not(server_task.done() or SHUTDOWN_EVENT.is_set()):
            await asyncio.sleep(server_config.rollover_check_poll_interval)
            modification_time: float = os.stat(server_config.certificate_filepath, follow_symlinks=False).st_mtime
            if modification_time != reference_time:
                # Close current listener socket, and break out of server_task loop to restart server with new credentials
                reference_time = modification_time
                server_task.cancel()
                break
        
        # Loop exit, check for shutdown condition and end task if true
        if SHUTDOWN_EVENT.is_set():
            server_task.cancel()
            return
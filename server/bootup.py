'''Helper module for loading all required instances whenever the server starts'''
import asyncio
import ssl
from functools import partial
from math import inf
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Optional, Sequence

from aiofiles.threadpool.binary import AsyncBufferedReader, AsyncBufferedIOBase

from cachetools import TTLCache

from models.flags import CategoryFlag

from server.authz.user_manager import UserManager
from server.callback import callback
from server.config.server_config import ServerConfig
from server.database.connections import ConnectionPoolManager
from server.dependencies import ServerSingletonsRegistry
from server.dispatch import auth_subhandler_mapping, file_subhandler_mapping, info_subhandler_mapping, permission_subhandler_mapping
from server.file_ops.storage import StorageCache
from server.logging import Logger
from server.process.events import EventProxy
from server.tls import credentials
from server.typing import RequestHandler, PartialisedRequestHandler

import pytomlpp

__all__ = ('create_server_config',
           'create_logger',
           'create_connection_master',
           'create_caches',
           'create_file_lock',
           'create_user_master',
           'create_storage_cache')

def create_server_config(dirname: Optional[str] = None) -> ServerConfig:
    loaded_constants: dict[str, dict[str, Any]] = pytomlpp.load(dirname or Path(__file__).parent.joinpath('config', 'server_config.toml'))

    flattened_dict: dict[str, Any] = {}
    leftover_mappings: list[dict[str, Any]] = [loaded_constants]
    while leftover_mappings:
        mapping = leftover_mappings.pop()
        for k, v in mapping.items():
            if isinstance(v, dict):
                leftover_mappings.append(mapping[k])
                continue
            flattened_dict.update({k:v})

    server_config: Final[ServerConfig] = ServerConfig.model_validate(flattened_dict)
    server_root: Final[Path] = Path(__file__).parent
    server_config.update_files_directory(server_root)
    server_config.finalise_credential_filepaths(credentials_directory=server_root / 'credentials')

    return server_config

async def create_connection_master(conninfo: str, config: ServerConfig,
                                   shutdown_poll_interval: int,
                                   shutdown_event: EventProxy,
                                   cleanup_event: asyncio.Event) -> ConnectionPoolManager:
    connection_master = ConnectionPoolManager(config.connection_lease_duration, *config.max_connections,
                                              connection_timeout=config.connection_timeout,
                                              connection_refresh_timer=config.connection_refresh_interval,
                                              shutdown_polling_interval=shutdown_poll_interval,
                                              shutdown_event=shutdown_event,
                                              cleanup_event=cleanup_event)
    
    await connection_master.populate_pools(conninfo)
    return connection_master

def create_user_master(connection_master: ConnectionPoolManager,
                       config: ServerConfig,
                       logger: Logger,
                       shutdown_poll_interval: float,
                       shutdown_event: EventProxy,
                       cleanup_event: asyncio.Event) -> UserManager:
    return UserManager(connection_master=connection_master,
                       logger=logger,
                       session_lifespan=config.session_lifespan,
                       shutdown_poll_time=shutdown_poll_interval,
                       shutdown_event=shutdown_event,
                       cleanup_event=cleanup_event)

def create_file_lock(config: ServerConfig) -> TTLCache[str, bytes]:
    return TTLCache(maxsize=inf, ttl=config.file_lock_ttl)

def create_caches(config: ServerConfig) -> tuple[TTLCache[str, dict[str, AsyncBufferedReader]],
                                                          TTLCache[str, dict[str, AsyncBufferedIOBase]],
                                                          TTLCache[str, str]]:
    
    read_cache = TTLCache(maxsize=config.file_cache_size, ttl=config.file_cache_ttl)
    amendment_cache = TTLCache(maxsize=config.file_cache_size, ttl=config.file_cache_ttl)
    delete_cache = TTLCache(maxsize=config.file_cache_size, ttl=config.file_cache_ttl)

    return read_cache, amendment_cache, delete_cache

def create_storage_cache(connection_master: ConnectionPoolManager,
                         server_config: ServerConfig,
                         shutdown_polling_interval: float,
                         shutdown_event: EventProxy,
                         cleanup_event: asyncio.Event) -> StorageCache:
    return StorageCache(connection_master=connection_master,
                        disk_flush_interval=server_config.disk_flush_interval,
                        flush_batch_size=server_config.disk_flush_batch_size,
                        shutdown_polling_interval=shutdown_polling_interval,
                        shutdown_event=shutdown_event,
                        cleanup_event=cleanup_event)

def create_logger(config: ServerConfig,
                  connection_master: ConnectionPoolManager,
                  shutdown_event: EventProxy,
                  cleanup_event: asyncio.Event) -> Logger:
    logger: Final[Logger] = Logger(waiting_period=config.log_waiting_period,
                                           connection_master=connection_master,
                                           batch_size=config.log_batch_size,
                                           flush_interval=config.log_interval,
                                           shutdown_event=shutdown_event,
                                           cleanup_event=cleanup_event)
    return logger

def partialise_request_subhandlers(singleton_registry: ServerSingletonsRegistry,
                                   top_handler_mapping: dict[CategoryFlag, RequestHandler],
                                   subhandler_mappings: Sequence[dict[Any, Any]]) -> MappingProxyType[CategoryFlag, PartialisedRequestHandler]:
    # Update actual references of request subhandlers
    for subhandler_mapping in subhandler_mappings:
        for subcategory_flag, request_handler in subhandler_mapping.items():
            subhandler_mapping[subcategory_flag] = singleton_registry.inject_global_singletons(request_handler, strict=False)

    partialised_mapping: Final[dict[CategoryFlag, PartialisedRequestHandler]] = {}
    partialised_mapping[CategoryFlag.AUTH] = partial(top_handler_mapping[CategoryFlag.AUTH], **{'subhandler_mapping' : auth_subhandler_mapping})
    partialised_mapping[CategoryFlag.INFO] = partial(top_handler_mapping[CategoryFlag.INFO], **{'subhandler_mapping' : info_subhandler_mapping})
    partialised_mapping[CategoryFlag.PERMISSION] = partial(top_handler_mapping[CategoryFlag.PERMISSION], **{'subhandler_mapping' : permission_subhandler_mapping})
    partialised_mapping[CategoryFlag.FILE_OP] = partial(top_handler_mapping[CategoryFlag.FILE_OP], **{'subhandler_mapping' : file_subhandler_mapping})

    return MappingProxyType(partialised_mapping)

async def start_server(dependency_registry: ServerSingletonsRegistry,
                       request_handler_map: MappingProxyType[CategoryFlag, PartialisedRequestHandler]) -> None:
    ssl_context: ssl.SSLContext = credentials.make_server_ssl_context(certfile=dependency_registry.server_config.certificate_filepath,
                                                                      keyfile=dependency_registry.server_config.key_filepath,
                                                                      ciphers=dependency_registry.server_config.ciphers)
    server: asyncio.Server = await asyncio.start_server(client_connected_cb=partial(callback, dependency_registry, request_handler_map),
                                                        host=str(dependency_registry.server_config.host), port=dependency_registry.server_config.port,
                                                        ssl=ssl_context)
    
    async with server:
        await server.serve_forever()
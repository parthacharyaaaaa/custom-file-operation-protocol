'''Utility modules for handling storage limits for users'''
import asyncio
from collections import OrderedDict
from typing import Optional, Final
import weakref

from server.database.connections import ConnectionPoolManager, ConnectionPriority, ConnectionProxy
from server.errors import UserNotFound, FileNotFound

from models.singletons import SingletonMetaclass

from psycopg.rows import dict_row, DictRow
from psycopg import sql

from server.process.events import EventProxy, ExclusiveEventProxy

__all__ = ('StorageData',
           'StorageCache')

class StorageData:
    __slots__ = ('filecount', 'storage_used', 'file_data')
    filecount: int
    storage_used: int
    file_data: dict[str, int]

    def __init__(self, filecount: int, storage_used: int):
        self.filecount = filecount
        self.storage_used = storage_used
        self.file_data = {}

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.filecount=}, {self.storage_used=}, {self.file_data=})'

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}({self.filecount=}, {self.storage_used=}, {self.file_data=}) at {hex(id(self))}>'

    @property
    def as_tuple(self) -> tuple[int, int]:
        return self.filecount, self.storage_used

class StorageCache(OrderedDict, metaclass=SingletonMetaclass):
    __slots__ = ('connection_master',
                 '_disk_flush_interval', '_flush_batch_size',
                 '_shutdown_polling_interval', '_shutdown_event', '_cleanup_event')
    
    storage_fetch_query: Final[sql.Composed] = (sql.SQL('''SELECT file_count AS {}, storage_used AS {} 
                                                        FROM users
                                                        WHERE username = %s;''')
                                                        .format(*(sql.Identifier(slot) for slot in StorageData.__slots__)))

    file_size_retrieval_query: Final[sql.SQL] = (sql.SQL('''SELECT file_size
                                                              FROM files
                                                              WHERE owner = %s AND filename = %s;'''))
    
    storage_flush_query: Final[sql.SQL] = (sql.SQL('''UPDATE users
                                                        SET file_count = %s, storage_used = %s
                                                        WHERE username = %s;'''))
    
    file_flush_query: Final[sql.SQL] = (sql.SQL('''UPDATE files
                                                     SET file_size = %s
                                                     WHERE owner = %s AND filename = %s;'''))
    
    def __init__(self,
                 connection_master: ConnectionPoolManager,
                 disk_flush_interval: float,
                 flush_batch_size: int,
                 shutdown_polling_interval: float,
                 shutdown_event: EventProxy,
                 cleanup_event: asyncio.Event):
        self.connection_master: Final[ConnectionPoolManager] = connection_master
        self._disk_flush_interval: float = disk_flush_interval
        self._flush_batch_size: int = flush_batch_size
        self._shutdown_polling_interval: float = shutdown_polling_interval
        self._shutdown_event: Final[EventProxy] = shutdown_event
        self._cleanup_event: Final[ExclusiveEventProxy] = ExclusiveEventProxy(cleanup_event, weakref.ref(self))
        super().__init__()

        storage_syncing_task: asyncio.Task[None] = asyncio.create_task(self.background_storage_sync())
        asyncio.create_task(self.shutdown_handler(storage_syncing_task))

    @property
    def disk_flush_interval(self) -> float:
        return self._disk_flush_interval
    @disk_flush_interval.setter
    def disk_flush_interval(self, value: float) -> None:
        if (value <= 0) or not isinstance(value, (float, int)):
            raise ValueError("Disk flush interval time must be a positive fraction")
        self._disk_flush_interval = value
    
    @property
    def shutdown_polling_interval(self) -> float:
        return self._shutdown_polling_interval
    @shutdown_polling_interval.setter
    def shutdown_polling_interval(self, value: float) -> None:
        if (value <= 0) or not isinstance(value, (float, int)):
            raise ValueError("Shutdown polling interval time must be a positive fraction")
        self._shutdown_polling_interval = value
    
    @property
    def flush_batch_size(self) -> float:
        return self._flush_batch_size
    @flush_batch_size.setter
    def flush_batch_size(self, value: int) -> None:
        if (value <= 0) or not isinstance(value, int):
            raise ValueError("Batch size time must be a positive integer")
        self._flush_batch_size = value

    async def get_storage_data(self,
                               username: str,
                               proxy: Optional[ConnectionProxy] = None,
                               release_after: bool = False) -> StorageData:
        current_storage: Optional[StorageData] = self.get(username)
        if current_storage:
            return current_storage
        
        if not proxy:
            release_after = True
            proxy = await self.connection_master.request_connection(level=ConnectionPriority.LOW)
        
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(StorageCache.storage_fetch_query, (username,))
            result: Optional[DictRow] = await cursor.fetchone()
        if release_after:
            await self.connection_master.reclaim_connection(proxy)
        
        if not result:
            raise UserNotFound(f'User {username} not found')
        
        return self.setdefault(username, StorageData(**result))
    
    async def update_file_size(self,
                               username: str,
                               diff: int,
                               proxy: Optional[ConnectionProxy] = None,
                               release_after: bool = False) -> int:
        await self.get_storage_data(username, proxy, release_after)
        self[username].storage_used += diff
        
        return self[username].storage_used

    async def update_file_count(self,
                                username: str,
                                file: str,
                                diff: int = 1,
                                proxy: Optional[ConnectionProxy] = None,
                                release_after: bool = False) -> int:
        if await self.get_storage_data(username, proxy, release_after):
            self[username].filecount += diff
            self[username].file_data.setdefault(file, 0)
            return self[username].filecount
        
        raise UserNotFound(f'Attempt to update file count for non-existent user {username}')
    
    async def get_file_size(self,
                            username: str,
                            file: str,
                            proxy: Optional[ConnectionProxy] = None,
                            release_after: bool = False) -> int:
        storage_data: Optional[StorageData] = self.get(username)
        if storage_data and (file_data:=storage_data.file_data.get(file)):
            return file_data
        
        if not proxy:
            proxy = await self.connection_master.request_connection(level=ConnectionPriority.LOW)
            release_after = True
        async with proxy.cursor() as cursor:
            if not storage_data:
                storage_data = await self.get_storage_data(username, proxy)

            await cursor.execute(StorageCache.file_size_retrieval_query, (username, file,))
            result = await cursor.fetchone()
            if not result:
                raise FileNotFound(file, username)
        
        if release_after:
            await self.connection_master.reclaim_connection(proxy)

        self.setdefault(username, storage_data)
        return self[username].file_data.setdefault(file, result[0])

    async def remove_file(self,
                          username: str,
                          file: str,
                          proxy: Optional[ConnectionProxy] = None,
                          release_after: bool = False) -> int:
        user_storage: Optional[StorageData] = await self.get_storage_data(username, proxy, release_after)
        if not user_storage:
            raise UserNotFound(f'Attempted to remove file from non-existent user: {username}')
        
        file_size: int = user_storage.file_data.pop(file) if file in user_storage.file_data else await self.get_file_size(username, file, proxy, release_after)

        user_storage.storage_used -= file_size
        user_storage.filecount -= 1
        return file_size
    
    async def reflect_removed_file(self,
                                   username: str,
                                   file_size: int,
                                   proxy: Optional[ConnectionProxy] = None) -> int:
        user_storage: Optional[StorageData] = await self.get_storage_data(username, proxy, True)
        if not user_storage:
            raise UserNotFound(f'Attempted to remove file from non-existent user: {username}')
        
        user_storage.storage_used -= file_size
        user_storage.filecount -= 1
        return user_storage.storage_used
    
    async def _flush_buffer(self, buffer: dict[str, StorageData]) -> None:
        async with await self.connection_master.request_connection(level=ConnectionPriority.LOW) as proxy:
            async with proxy.cursor() as cursor:
                await cursor.executemany(StorageCache.storage_flush_query,
                                         ((user_storage_data.filecount, user_storage_data.storage_used, username)
                                          for username, user_storage_data in buffer.items()))
                await cursor.executemany(StorageCache.file_flush_query,
                                         ((size, username, file)
                                          for username, user_storage_data in buffer.items()
                                          for file, size in user_storage_data.file_data.items()))
            await proxy.commit()
    
    async def shutdown_handler(self, storage_syncing_task: asyncio.Task) -> None:
        while not self._shutdown_event.is_set(): await asyncio.sleep(self._shutdown_polling_interval)

        storage_syncing_task.cancel()
        if self:
            await self._flush_buffer(self.copy())
            self.clear()
        self._cleanup_event.set(self)
    
    async def background_storage_sync(self) -> None:
        current_buffer: dict[str, StorageData] = {}
        while True:
            while self and len(current_buffer) <= self.flush_batch_size:
                storage_item, storage_data =  self.popitem(last=False)
                current_buffer[storage_item] = storage_data
                
            await self._flush_buffer(current_buffer)
            current_buffer.clear()
            await asyncio.sleep(self.disk_flush_interval)

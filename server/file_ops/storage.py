'''Utility modules for handling storage limits for users'''
import asyncio
from collections import OrderedDict
from typing import Optional, Final

from server.database.connections import ConnectionPoolManager, ConnectionProxy
from server.errors import UserNotFound, FileNotFound

from models.singletons import SingletonMetaclass

from psycopg.rows import dict_row
from psycopg import sql

__all__ = ('StorageData',
           'StorageCache')

class StorageData:
    __slots__ = ('filecount', 'storage_left')
    filecount: int
    storage_left: int
    file_data: dict[str, int]

    def __init__(self, filecount: int, storage_left: int):
        self.filecount = filecount
        self.storage_left = storage_left
        self.file_data = {}

    @property
    def as_tuple(self) -> tuple[str, str]:
        return self.filecount, self.storage_left

class StorageCache(OrderedDict, metaclass=SingletonMetaclass):
    __slots__ = ('connection_master', 'disk_flush_interval', 'flush_batch_size')
    
    storage_fetch_query: Final[sql.SQL] = (sql.SQL('''SELECT file_count AS {}, storage_used AS {} 
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
                                                   SET file_storage = %s
                                                   WHERE owner = %s AND filename = %s;'''))
    
    def __init__(self,
                 connection_master: ConnectionPoolManager,
                 disk_flush_interval: float,
                 flush_batch_size: int):
        self.connection_master = connection_master
        self.disk_flush_interval = disk_flush_interval
        self.flush_batch_size = flush_batch_size
        super().__init__()

        asyncio.create_task(self.background_storage_sync())

    async def get_storage_data(self,
                               username: str,
                               proxy: Optional[ConnectionProxy] = None,
                               release_after: bool = False,
                               raise_on_missing: bool = False) -> Optional[StorageData]:
        current_storage: Optional[StorageData] = self.get(username)
        if current_storage:
            return current_storage
        
        if not proxy:
            release_after = True
            proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)
        
        async with proxy.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(StorageCache.storage_fetch_query, (username,))
            result: Optional[dict[str, int]] = await cursor.fetchone()
        if release_after:
            await self.connection_master.reclaim_connection(proxy)
        
        if not result:
            if raise_on_missing:
                raise UserNotFound(f'User {username} not found')
            return None
        
        return self.setdefault(username, StorageData(**result))
    
    async def update_file_size(self,
                               username: str,
                               diff: int,
                               proxy: Optional[ConnectionProxy] = None,
                               release_after: bool = False) -> int:
        if await self.get_storage_data(username, proxy, release_after):
            self[username].storage_left += diff
        
        return self[username].storage_left

    async def update_file_count(self,
                                username: str,
                                file: str,
                                diff: int = 1,
                                proxy: Optional[ConnectionProxy] = None,
                                release_after: bool = False) -> None:
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
            proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)
            release_after = True
        async with proxy.cursor() as cursor:
            if not storage_data:
                storage_data = await self.get_storage_data(username, proxy, raise_on_missing=True)

            await cursor.execute(StorageCache.file_size_retrieval_query, (username, file,))
            file_size = await cursor.fetchone()
            if not file_size:
                raise FileNotFound(f'No file named {file} under user {username}')
            

        if release_after:
            await self.connection_master.reclaim_connection(proxy)

        self.setdefault(storage_data)
        return self[username].file_data.setdefault(file, file_size)

    async def remove_file(self,
                          username: int,
                          file: str,
                          proxy: Optional[ConnectionProxy] = None,
                          release_after: bool = False) -> None:
        user_storage: Optional[StorageData] = await self.get_storage_data(username, ConnectionProxy, release_after)
        if not user_storage:
            raise UserNotFound(f'Attempted to remove file from non-existent user: {username}')

        if file in user_storage.file_data:
            user_storage.storage_left += user_storage.file_data.pop(file)
        else:
            file_size = await self.get_file_size(username, file, proxy, release_after)
            user_storage.storage_left += file_size

        return user_storage.storage_left
    
    async def _flush_buffer(self, buffer: dict[str, StorageData]) -> None:
        async with await self.connection_master.request_connection(level=1) as proxy:
            async with proxy.cursor() as cursor:
                await cursor.executemany(StorageCache.storage_flush_query,
                                         ((user_storage_data.filecount, user_storage_data.storage_left, username)
                                          for username, user_storage_data in buffer.items()))
                await cursor.executemany(StorageCache.file_flush_query,
                                         ((size, username, file)
                                          for username, user_storage_data in buffer.items()
                                          for file, size in user_storage_data.file_data.items()))
            await proxy.commit()
        buffer = {}
    
    async def background_storage_sync(self) -> None:
        current_buffer: dict[str, StorageData] = {}
        while True:
            while self and len(current_buffer) <= self.flush_batch_size:
                popped_item: tuple[str, StorageData] =  self.popitem(last=False)
                current_buffer[popped_item[0]] = popped_item[1]
            
            await self._flush_buffer(current_buffer)
            await asyncio.sleep(self.disk_flush_interval)

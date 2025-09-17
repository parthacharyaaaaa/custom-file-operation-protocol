import asyncio
from contextlib import asynccontextmanager
from typing import Literal, Optional, NoReturn, overload, Protocol, AsyncIterator, TYPE_CHECKING, Union
from typing_extensions import Self
from types import TracebackType, FunctionType
from uuid import uuid4

import psycopg as pg
from psycopg.abc import Query, Params
from psycopg.rows import Row, DictRow, TupleRow
from psycopg.transaction import AsyncTransaction

__all__ = ('SupportsConnection', 'ConnectionPoolManager', 'LeasedConnection', 'ConnectionProxy')

class SupportsConnection(Protocol):
    '''Protocol supporting interface to psycopg's connection's methods'''
    def info(self) -> pg.ConnectionInfo: ...

    @overload
    def cursor(self, *,
               binary: bool = False,
               row_factory: None = None,
               **kwargs) -> pg.AsyncCursor[TupleRow]: pass

    @overload
    def cursor(self, *,
               binary: bool = False,
               row_factory: FunctionType,
               **kwargs) -> pg.AsyncCursor[DictRow]: pass

    def cursor(self, *,
               binary: bool = False,
               row_factory: Optional[FunctionType] = None,
               **kwargs) -> Union[pg.AsyncCursor[TupleRow], pg.AsyncCursor[DictRow]]: ...

    async def execute(self, query: Query, params: Params | None = None, *, prepare: bool | None = None, binary: bool = False) -> pg.AsyncCursor[Row]: ...
   
    async def rollback(self) -> None: ...
    
    async def cancel_safe(self, *, timeout: float = 30.0) -> None: ...
    
    async def commit(self) -> None: ...
    
    @asynccontextmanager    #type: ignore
    async def transaction(self, savepoint_name: str | None = None, force_rollback: bool = False) -> AsyncIterator[AsyncTransaction]: ...


class ConnectionProxy(SupportsConnection if TYPE_CHECKING else object):
    '''Proxy object for a database connection leased from a ConnectionPoolManager instance'''
    __slots__ = '_token', '_conn'
    def __init__(self, leased_conn: 'LeasedConnection', token: str):
        self._conn = leased_conn
        self._token = token

    @property
    def token(self) -> str:
        return self._token
    @property
    def conn(self) -> str:
        return repr(self._conn)
    
    def __getattr__(self, name):
        attr = getattr(self._conn, name)
        if callable(attr):
            if self.token != self._conn._usage_token:
                raise PermissionError('Lease expired for this connection')
            
            if asyncio.iscoroutinefunction(attr):
                async def coro(*args, **kwargs):
                    return await attr(*args, **kwargs)
                return coro
            else:
                def wrapped(*args, **kwargs):
                    return attr(*args, **kwargs)
                return wrapped
        
        return attr
    
    async def __aenter__(self) -> Self:
        if self.token != self._conn._usage_token:
            raise PermissionError('Lease expired for this connection')
        return self
    
    async def __aexit__(self,
                         exc_type: type[BaseException] | None,
                         exc_val: BaseException | None,
                         exc_tb: TracebackType | None) -> None:
        await self._conn._manager.reclaim_connection(proxy=self)

class LeasedConnection:
    '''Abstraction over `pg.AsyncConnection` to allow for enforcing a timed leased on the underlying connection to the database server.
    Automatically invalidated once lease duration is expired'''
    exempt_methods: frozenset[str] = frozenset('release')

    __slots__ = ('_pgconn', '_manager', '_lease_duration', '_lease_expired', '_in_use', '_priority', '_usage_token')

    def __init__(self, pgconn: pg.AsyncConnection, manager: 'ConnectionPoolManager', lease_duration: float, priority: int, **kwargs):
        self._pgconn = pgconn
        self._manager = manager
        self._lease_duration: float = lease_duration
        self._lease_expired: bool = False
        self._in_use: bool = False
        self._priority: int = priority
        self._usage_token: Optional[str] = None

    @classmethod
    async def connect(cls, conninfo: str, manager: 'ConnectionPoolManager', lease_duration: float, priority: int, **kwargs) -> 'LeasedConnection':
        pgconn = await pg.AsyncConnection.connect(conninfo=conninfo, **kwargs)
        return cls(pgconn, manager, lease_duration, priority)
    
    @property
    def priority(self) -> int:
        return self._priority
    @priority.setter
    def priority(self, value) -> NoReturn:
        raise TypeError('LeasedConnection.priority is read-only and required to be untampered for proper reclaims')

    @property
    def manager(self) -> 'ConnectionPoolManager':
        return self._manager
    @manager.setter
    def manager(self, value) -> NoReturn:
        raise TypeError('LeasedConnection.manager is read-only')
    
    @property
    def lease_duration(self) -> float:
        return self._lease_duration
    
    @property
    def lease_expired(self) -> bool:
        return self._lease_expired
    @lease_expired.setter
    def lease_expired(self, value: bool) -> NoReturn:
        raise TypeError('Lease expired is a read-only attribute.')
    
    def _set_usage(self, token: str):
        if self._usage_token:
            raise TypeError('Connection currently leased')
        self._usage_token = token
        self._in_use = True

    def _reset_usage(self):
        self._usage_token = None
        self._in_use = False
        self._lease_expired = False

    async def begin_lease_timer(self):
        await asyncio.sleep(self.lease_duration)
        self._lease_expired = True
        if self._usage_token:
            await self.return_to_pool()

    async def return_to_pool(self):
        self._reset_usage()
    
    def __getattr__(self, name):
        attr = getattr(self._pgconn, name)
        
        if callable(attr):
            if self._lease_expired:
                raise TimeoutError('This connection is expired')
            if not self._in_use:
                raise TypeError('Connection not in use. Leaase a connection from the pool to use it')
            
            if asyncio.iscoroutinefunction(attr):
                async def coro(*args, **kwargs):
                    return await attr(*args, **kwargs)
                return coro
            else:
                def wrapped(*args, **kwargs):
                    return attr(*args, **kwargs)
                return wrapped
        
        return attr

class ConnectionPoolManager:
    '''Manager for maintaining different connection pools to the Postgres server'''
    __slots__ = ('connection_timeout', 'lease_duration', 'refresh_timer',
                 '_hp_connection_pool', '_mp_connection_pool', '_lp_connection_pool')
    
    def __init__(self, lease_duration: float, high_priority_conns: int, mid_priority_conns: int, low_priority_conns: int, connection_timeout: float = 10, connection_refresh_timer: float = 600) -> None:
        if connection_timeout <= 0:
            raise ValueError('Connection timeout must be positive')
        if connection_refresh_timer <= 0:
            raise ValueError('Connection refresh timer must be positive')
        if lease_duration <= 0:
            raise ValueError('Maximum lease duration must be positive')

        self.connection_timeout: float = connection_timeout
        self.refresh_timer: float = connection_refresh_timer
        self.lease_duration: float = lease_duration

        # Create connection pools as queue and populate them with AsyncConnection objects
        self._hp_connection_pool: asyncio.Queue[LeasedConnection] = asyncio.Queue(maxsize=high_priority_conns)
        self._mp_connection_pool: asyncio.Queue[LeasedConnection] = asyncio.Queue(maxsize=mid_priority_conns)
        self._lp_connection_pool: asyncio.Queue[LeasedConnection] = asyncio.Queue(maxsize=low_priority_conns)

    async def populate_pools(self, conninfo: str) -> None:
        for _ in range(self._hp_connection_pool.maxsize):
            await self._hp_connection_pool.put(await LeasedConnection.connect(conninfo, self, self.lease_duration, 1, autocommit=True))
        for _ in range(self._mp_connection_pool.maxsize):
            await self._mp_connection_pool.put(await LeasedConnection.connect(conninfo, self, self.lease_duration, 2, autocommit=True))
        for _ in range(self._lp_connection_pool.maxsize):
            await self._lp_connection_pool.put(await LeasedConnection.connect(conninfo, self, self.lease_duration, 3, autocommit=True))

    async def request_connection(self, level: Literal[1,2,3], max_lease_duration: Optional[float] = None) -> ConnectionProxy:
        '''Request a connection from one of the priority pools. If none available, waits.
        Args:
            level (int): Priority of the operation
            max_lease_duration (Optional[float]): Optional timeout for the connection. If given, the connection will automatically be revoked after the specified time
        Returns:
            AsyncConnection object
        '''
        pool = self._hp_connection_pool if level == 1 else self._mp_connection_pool if level == 2 else self._lp_connection_pool
        requested_connection: LeasedConnection = await pool.get()
        
        token: str = uuid4().hex
        requested_connection._set_usage(token)
        max_lease_duration = min(self.lease_duration, (max_lease_duration or self.lease_duration))

        requested_connection._lease_duration = max_lease_duration
        proxy: ConnectionProxy = ConnectionProxy(leased_conn=requested_connection, token=token) # type: ignore
        asyncio.create_task(requested_connection.begin_lease_timer())

        return proxy
    
    async def reclaim_connection(self, proxy: ConnectionProxy) -> None:
        if proxy._conn.manager != self:
            raise ValueError(f'Connection not reclaimable as it does not belong to this instance of {self.__class__.__name__}')
        
        proxy._conn._reset_usage()
        if proxy._conn.priority == 1:
            await self._hp_connection_pool.put(proxy._conn)
        elif proxy._conn.priority == 2:
            await self._mp_connection_pool.put(proxy._conn)
        else:
            await self._lp_connection_pool.put(proxy._conn)
    
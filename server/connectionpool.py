import psycopg as pg
import asyncio
from typing import Literal, Optional, NoReturn
from uuid import uuid4
from warnings import warn

class ConnectionProxy:
    def __init__(self, leased_conn: 'LeasedConnection', token: str):
        self._conn = leased_conn
        self._token = token

    
    def check_lease_validity(self) -> bool:
        return self._conn._usage_token == self._token and self._conn._in_use and not self._conn.lease_expired
    
    def assert_lease_validity(self) -> NoReturn:
        assert self._conn._usage_token == self._token and self._conn._in_use and not self._conn.lease_expired,\
            'Token invalid for leased connection'

    def __getattr__(self, name):
        attr = getattr(self._conn._pgconn, name)

        if callable(attr):
            self.assert_lease_validity()
            if asyncio.iscoroutinefunction(attr):
                async def wrapped(*args, **kwargs): 
                    return await attr(*args, **kwargs)
                return wrapped
            else:
                def wrapped(*args, **kwargs):
                    return attr(*args, **kwargs)
                return wrapped
        
        return attr

class LeasedConnection:
    exempt_methods: frozenset[str] = frozenset('release')
    def __init__(self, pgconn: pg.AsyncConnection, manager: 'ConnectionPoolManager', lease_duration: float, **kwargs):
        self._pgconn = pgconn
        self._manager = manager
        self._lease_duration: float = lease_duration
        self._lease_expired: bool = False
        self._in_use: bool = False

    @classmethod
    async def connect(cls, conninfo: str, manager: 'ConnectionPoolManager', lease_duration: float, **kwargs) -> 'LeasedConnection':
        pgconn = await pg.AsyncConnection.connect(conninfo=conninfo, **kwargs)
        return cls(pgconn, manager, lease_duration)

    @property
    def manager(self) -> 'ConnectionPoolManager':
        return self._manager
    @manager.setter
    def manager(self, value) -> NoReturn:
        raise TypeError('LeasedConnection.manager is read-only')
    
    @property
    def lease_duration(self) -> float:
        return self._lease_duration
    
    def _set_usage_token(self, token: Optional[str] = None):
        self._usage_token = token
    
    @property
    def lease_expired(self) -> bool:
        return self._lease_expired
    @lease_expired.setter
    def lease_expired(self, value: bool) -> NoReturn:
        raise TypeError('Lease expired is a read-only attribute.')

    async def begin_lease_timer(self):
        await asyncio.sleep(self.lease_duration)
        self._lease_expired = True
        await self.return_to_pool()

    async def return_to_pool(self):
        await self.manager.reclaim_connection(self)

    #TODO: Add token validation logic for database cursor and any objects that may use this connection.
    def __getattribute__(self, name: str):
        if name.startswith('_') or name in LeasedConnection.exempt_methods:
            return super().__getattribute__(name)
        
        attr = object.__getattribute__(self, name)
        if callable(attr):
            if self.lease_expired:
                raise TimeoutError('This connection is expired')
        return attr

class ConnectionPoolManager:
    async def __init__(self, conninfo: str, lease_duration: float, high_priority_conns: int, mid_priority_conns: int, low_priority_conns: int, connection_timeout: float = 10, connection_refresh_timer: float = 600) -> None:
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
        self._hp_connection_pool: asyncio.Queue = asyncio.Queue(maxsize=high_priority_conns)
        self._mp_connection_pool: asyncio.Queue = asyncio.Queue(maxsize=high_priority_conns)
        self._lp_connection_pool: asyncio.Queue = asyncio.Queue(maxsize=high_priority_conns)

        pg.AsyncConnection.connect
        for _ in range(high_priority_conns):
            self._hp_connection_pool.put(await LeasedConnection.connect(conninfo, self, lease_duration, autocommit=True))
        for _ in range(mid_priority_conns):
            self._mp_connection_pool.put(await LeasedConnection.connect(conninfo, self, lease_duration, autocommit=True))
        for _ in range(low_priority_conns):
            self._lp_connection_pool.put(await LeasedConnection.connect(conninfo, self, lease_duration, autocommit=True))
        
    async def request_connection(self, level: Literal[1,2,3], max_lease_duration: Optional[float] = None) -> pg.AsyncConnection:
        '''Request a connection from one of the priority pools. If none available, waits.
        Args:
            level (int): Priority of the operation
            max_lease_duration (Optional[float]): Optional timeout for the connection. If given, the connection will automatically be revoked after the specified time
        Returns:
            AsyncConnection object
        '''
        requested_connection: LeasedConnection = None
        if level == 1:
            requested_connection = await self._hp_connection_pool.get()
        elif level == 2:
            requested_connection  = await self._mp_connection_pool.get()
        elif level == 3:
            requested_connection = await self._lp_connection_pool.get()
        else:
            raise ValueError('Invalid connection priority level provided')
        
        token: str = uuid4().hex
        requested_connection._set_usage_token(token)
        if max_lease_duration < self.lease_duration:
            warn(f'Requested lease duration cannot be higher than {self.lease_duration}. Requested connection will now have lease duration of {self.lease_duration} and not {max_lease_duration}', type=UserWarning)
            max_lease_duration = self.lease_duration

        requested_connection._lease_duration = max_lease_duration
        proxy: ConnectionProxy = ConnectionProxy(leased_conn=requested_connection, token=token)
        asyncio.create_task(requested_connection.begin_lease_timer())

        return proxy
    
    async def reclaim_connection(self, conn: LeasedConnection) -> None:
        if conn.manager != self:
            raise ValueError(f'Connection not reclaimable as it does not belong to this instance of {self.__class__.__name__}')
        
        conn._in_use = False
        conn._usage_token = None
        conn._lease_duration = self.lease_duration

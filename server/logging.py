import asyncio
import weakref
from typing import Final, Sequence
from traceback import format_exception_only

from server.database.connections import ConnectionPriority, ConnectionProxy, ConnectionPoolManager
from server.database.models import ActivityLog, LogAuthor, LogType, Severity
from server.process.events import EventProxy, ExclusiveEventProxy

from psycopg import sql
from psycopg import errors as pg_errors

__all__ = ('RECOVERABLE_ERRORS', 'Logger')

RECOVERABLE_ERRORS: Final[tuple[type[pg_errors.Error], ...]] = (pg_errors.ConnectionTimeout,
                                                                pg_errors.OperationalError,
                                                                pg_errors.InterfaceError)

LOG_INSERTION_SQL: Final[sql.Composed] = (sql.SQL('''INSERT INTO {tablename} ({columns_template})
                                                  VALUES ({placeholder_template});''')
                                                  .format(tablename=sql.Identifier('activity_logs'),
                                                          columns_template=sql.SQL(', ').join([sql.Identifier(key)
                                                                                               for key in list(ActivityLog.model_fields.keys())]),
                                                          placeholder_template=sql.SQL(', ').join([sql.Placeholder()
                                                                                                   for _ in range(len(ActivityLog.model_fields))])))
class Logger:
    __slots__ = ('__weakref__',
                 '_log_queue', 'connection_master',
                 '_batch_size', '_flush_interval', '_max_retries', '_waiting_period',
                 '_shutdown_event', '_cleanup_event', '_shutdown_polling_interval')
    
    def __init__(self,
                 waiting_period: float,
                 connection_master: ConnectionPoolManager,
                 batch_size: int,
                 flush_interval: float,
                 shutdown_polling_interval: float,
                 shutdown_event: EventProxy,
                 cleanup_event: asyncio.Event,
                 max_retries: int = 3):
        # System coordination
        self._shutdown_event: Final[EventProxy] = shutdown_event
        self._cleanup_event: Final[ExclusiveEventProxy] = ExclusiveEventProxy(cleanup_event, weakref.ref(self))
        
        # Internal Timing
        self._batch_size: int = batch_size
        self._max_retries: int = max_retries
        self._flush_interval: float = flush_interval
        self._waiting_period: float = waiting_period
        self._shutdown_polling_interval = shutdown_polling_interval

        # Database interactions
        self.connection_master: Final[ConnectionPoolManager] = connection_master
        self._log_queue: Final[asyncio.Queue[ActivityLog]] = asyncio.Queue()

        # Background tasks
        log_flush_task: Final[asyncio.Task[None]] = asyncio.create_task(self.flush_logs())
        asyncio.create_task(self.shutdown_handler(log_flush_task))
    
    @property
    def batch_size(self) -> int:
        return self._batch_size
    @batch_size.setter
    def batch_size(self, value: int) -> None:
        if (value <= 0) or not isinstance(value, int):
            raise ValueError("Batch size must be a positive integer")
        self._batch_size = value
    
    @property
    def max_retries(self) -> int:
        return self._max_retries
    @max_retries.setter
    def max_retries(self, value: int) -> None:
        if (value <= 0) or not isinstance(value, int):
            raise ValueError("Max retries for failed logs must be a positive integer")
        self._max_retries = value
    
    @property
    def waiting_period(self) -> float:
        return self._waiting_period
    @waiting_period.setter
    def waiting_period(self, value: float) -> None:
        if (value <= 0) or not isinstance(value, (float, int)):
            raise ValueError("Log entry waiting period must be a positive fraction")
        self._waiting_period = value
    
    @property
    def flush_interval(self) -> float:
        return self._flush_interval
    @flush_interval.setter
    def flush_interval(self, value: float) -> None:
        if (value <= 0) or not isinstance(value, (float, int)):
            raise ValueError("Log flush interval must be a positive fraction")
        self._flush_interval = value

    async def enqueue_log(self, log: ActivityLog) -> None:
        try:
            await asyncio.wait_for(self._log_queue.put(log), timeout=self.waiting_period)
        except asyncio.TimeoutError:
            return

    async def _flush_batch(self,
                           batch: Sequence[ActivityLog],
                           priority: ConnectionPriority = ConnectionPriority.LOW) -> None:
        proxy: ConnectionProxy = await self.connection_master.request_connection(level=priority)
        async with proxy.cursor() as cursor:
            await cursor.executemany(LOG_INSERTION_SQL,
                                    tuple(list(log_entry.model_dump().values()) for log_entry in batch))
        await proxy.commit()

    async def _emit_meta_log(self, pg_error: pg_errors.Error) -> None:
        try:
            async with await self.connection_master.request_connection(ConnectionPriority.HIGH) as proxy:
                async with proxy.cursor() as cursor:
                    meta_log = ActivityLog(
                        reported_severity=Severity.CRITICAL_FAILURE,
                        logged_by=LogAuthor.EXCEPTION_FALLBACK,
                        log_category=LogType.DATABASE,
                        log_details="\n".join(format_exception_only(pg_error)),
                    )
                    await cursor.execute(
                        LOG_INSERTION_SQL,
                        tuple(meta_log.model_dump().values()),
                    )
            await proxy.commit()
        except Exception:
            pass

    async def _flush_with_retries(self,
                                  batch: list[ActivityLog],
                                  priority: ConnectionPriority) -> None:
        for retry in range(self.max_retries):
            try:
                await self._flush_batch(batch, priority)
                batch.clear()
                return
            except pg_errors.Error as pg_error:
                if isinstance(pg_error, RECOVERABLE_ERRORS):
                    await asyncio.sleep(self.waiting_period)
                    continue

                await self._emit_meta_log(pg_error)
                batch.clear()
                return

        # retries exhausted, drop intentionally
        batch.clear()

    async def shutdown_handler(self, log_task: asyncio.Task[None]) -> None:
        while not self._shutdown_event.is_set(): await asyncio.sleep(self._shutdown_polling_interval)
        
        log_task.cancel()
        log_entries: list[ActivityLog] = []
        while not self._log_queue.empty():
            log_entries.append(self._log_queue.get_nowait())
        
        await self._flush_with_retries(log_entries, ConnectionPriority.HIGH)
        self._cleanup_event.set(self)

    async def flush_logs(self) -> None:
        log_entries: list[ActivityLog] = []
        while True:
            try:
                for _ in range(self.batch_size):
                    log_entries.append((await asyncio.wait_for(self._log_queue.get(), timeout=self.waiting_period)))  # Fetch only ActivityLog object in tuple at 0 index
            except asyncio.TimeoutError:
                if not log_entries:
                    continue
            
            await self._flush_with_retries(log_entries, ConnectionPriority.LOW)
            
            await asyncio.sleep(self.flush_interval)

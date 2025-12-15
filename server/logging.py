import asyncio
from typing import Optional, Final, Sequence
from traceback import format_exception_only

from server.database.connections import ConnectionPriority, ConnectionProxy, ConnectionPoolManager
from server.database.models import ActivityLog, LogAuthor, LogType, Severity
from server.datastructures import EventProxy

from psycopg import sql
from psycopg import errors as pg_errors

__all__ = ('enqueue_log',
           'flush_logs',
           'LOG_INSERTION_SQL')

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

async def enqueue_log(log: ActivityLog, queue: asyncio.Queue[ActivityLog], waiting_period: Optional[float] = None) -> None:
    try:
        await asyncio.wait_for(queue.put(log), timeout=waiting_period)
    except asyncio.TimeoutError:
        return

async def _flush_batch(connection_master: ConnectionPoolManager,
                       batch: Sequence[ActivityLog],
                       priority: ConnectionPriority = ConnectionPriority.LOW) -> None:
    proxy: ConnectionProxy = await connection_master.request_connection(level=priority)
    async with proxy.cursor() as cursor:
        await cursor.executemany(LOG_INSERTION_SQL,
                                tuple(list(log_entry.model_dump().values()) for log_entry in batch))
    await proxy.commit()

async def _emit_meta_log(connection_master: ConnectionPoolManager, pg_error: pg_errors.Error) -> None:
    try:
        async with await connection_master.request_connection(ConnectionPriority.HIGH) as proxy:
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

async def _flush_with_retries(connection_master: ConnectionPoolManager,
                              batch: list[ActivityLog],
                              priority: ConnectionPriority,
                              retries: int, backoff: float) -> None:
    for retry in range(retries):
        try:
            await _flush_batch(connection_master, batch, priority)
            batch.clear()
            return
        except pg_errors.Error as pg_error:
            if isinstance(pg_error, RECOVERABLE_ERRORS):
                await asyncio.sleep(backoff)
                continue

            await _emit_meta_log(connection_master, pg_error)
            batch.clear()
            return

    # retries exhausted, drop intentionally
    batch.clear()

async def flush_logs(connection_master: ConnectionPoolManager,
                     queue: asyncio.Queue[ActivityLog],
                     shutdown_event: EventProxy,
                     batch_size: int,
                     waiting_period: float, flush_interval: float,
                     retries: int = 3) -> None:
    log_entries: list[ActivityLog] = []
    while not shutdown_event.is_set():
        try:
            for _ in range(batch_size):
                log_entries.append((await asyncio.wait_for(queue.get(), timeout=waiting_period)))  # Fetch only ActivityLog object in tuple at 0 index
        except asyncio.TimeoutError:
            if not log_entries:
                continue
        
        await _flush_with_retries(connection_master,
                                  log_entries,
                                  ConnectionPriority.LOW,
                                  retries,
                                  waiting_period)
        
        await asyncio.sleep(flush_interval)
    
    # Shutdown event triggered
    while not queue.empty():
        log_entries.append(queue.get_nowait())
        await _flush_with_retries(connection_master,
                                  log_entries,
                                  ConnectionPriority.HIGH,
                                  retries,
                                  waiting_period // 2)
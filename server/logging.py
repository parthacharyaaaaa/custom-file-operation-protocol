import asyncio
from typing import Optional, Final
from traceback import format_exception_only

from server.database.connections import ConnectionPriority, ConnectionProxy, ConnectionPoolManager
from server.database.models import ActivityLog, Severity
from server.datastructures import EventProxy

from psycopg import sql

__all__ = ('enqueue_log',
           'flush_logs',
           'LOG_INSERTION_SQL')

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
    
async def flush_logs(connection_master: ConnectionPoolManager,
                     queue: asyncio.Queue[ActivityLog],
                     shutdown_event: EventProxy,
                     batch_size: int,
                     waiting_period: float, flush_interval: float) -> None:
    log_entries: list[ActivityLog] = []
    while not shutdown_event.is_set():
        try:
            for _ in range(batch_size):
                log_entries.append((await asyncio.wait_for(queue.get(), timeout=waiting_period)))  # Fetch only ActivityLog object in tuple at 0 index
        except asyncio.TimeoutError:
            if not log_entries:
                continue
        
        proxy: ConnectionProxy = await connection_master.request_connection(level=ConnectionPriority.LOW)
        try:
            async with proxy.cursor() as cursor:
                await cursor.executemany(LOG_INSERTION_SQL,
                                        tuple(list(log_entry.model_dump().values()) for log_entry in log_entries))
            await proxy.commit()
        except Exception as e:
            async with proxy.cursor() as cursor:
                await cursor.execute(LOG_INSERTION_SQL,
                                    (list(ActivityLog(reported_severity=Severity.CRITICAL_FAILURE, log_details=format_exception_only(e)[0]).model_dump().values())),)
            await proxy.commit()
        finally:
            await connection_master.reclaim_connection(proxy)
        
        log_entries.clear()
        await asyncio.sleep(flush_interval)
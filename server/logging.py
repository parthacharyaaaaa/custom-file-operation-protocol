import asyncio

from server.connectionpool import ConnectionProxy, ConnectionPoolManager
from server.database.models import ActivityLog

from psycopg import sql

__all__ = ('flush_logs', 'LOG_INSERTION_SQL')

LOG_INSERTION_SQL: sql.SQL = (sql.SQL('''INSERT INTO {tablename} ({columns_template})
                                        VALUES ({placeholder_template});''')
                                        .format(tablename=sql.Identifier('activity_logs'),
                                                columns_template=sql.SQL(', ').join([sql.Identifier(key) for key in list(ActivityLog.model_fields.keys())]),
                                                placeholder_template=sql.SQL(', ').join([sql.Placeholder() for _ in range(len(ActivityLog.model_fields))])))

async def flush_logs(connection_master: ConnectionPoolManager, queue: asyncio.PriorityQueue[ActivityLog], batch_size: int, waiting_period: float, flush_interval: float) -> None:
    log_entries: list[ActivityLog] = []
    while True:
        try:
            for _ in range(batch_size):
                log_entries.append(await asyncio.wait_for(queue.get(), timeout=waiting_period))
        except asyncio.TimeoutError:
            if not log_entries:
                continue    
        proxy: ConnectionProxy = await connection_master.request_connection(level=3)
        try:
            async with proxy.cursor() as cursor:
                await cursor.executemany(LOG_INSERTION_SQL,
                                        tuple(list(log_entry.model_dump().values()) for log_entry in log_entries))
            await proxy.commit()
        except Exception as e:
            async with proxy.cursor() as cursor:
                await cursor.execute(LOG_INSERTION_SQL,
                                    (list(ActivityLog(severity=5, log_details=e.__class__.__name__).model_dump().values())),)
            await proxy.commit()
        finally:
            await connection_master.reclaim_connection(proxy)
        
        await asyncio.sleep(flush_interval)
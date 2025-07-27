import asyncio
from typing import Optional, Union, Literal
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BaseFileComponent, BasePermissionComponent

STREAM_LOCK: asyncio.Lock = asyncio.Lock()

async def send_request(writer: asyncio.StreamWriter,
                       header_component: BaseHeaderComponent,
                       lock_contention_timmeout: float = 3.0,
                       auth_component: Optional[BaseAuthComponent] = None,
                       body_component: Optional[Union[BaseFileComponent, BasePermissionComponent]] = None) -> None:
    auth_stream = b'' if not auth_component else auth_component.model_dump_json().encode('utf-8')
    body_stream = b'' if not body_component else body_component.model_dump_json().encode('utf-8')

    header_component.auth_size = len(auth_stream)
    header_component.body_size = len(body_stream)

    acquired: Literal[True] = await asyncio.wait_for(STREAM_LOCK.acquire(), lock_contention_timmeout)
    try:
        writer.write(header_component.model_dump_json().encode('utf-8'))
        writer.write(auth_stream)
        writer.write(body_stream)

        await writer.drain()
    finally:
        STREAM_LOCK.release()
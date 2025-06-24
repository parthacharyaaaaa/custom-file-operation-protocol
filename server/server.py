import asyncio
from functools import partial
from server import response_codes
from server.config import ServerConfig, CategoryFlag
from server.authz.session_master import SessionMaster
from server.models.request_model import BaseHeaderComponent, BaseAuthComponent
from server.comms_utils.incoming import process_header, process_auth
from server.comms_utils.outgoing import send_heartbeat
from server.dispatch import TOP_LEVEL_REQUEST_MAPPING

async def callback(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_master: SessionMaster) -> None:
    header_component: BaseHeaderComponent = await process_header(ServerConfig.HEADER_READ_BYTESIZE, reader, writer)
    if not header_component:
        return
    
    # On heartbeat signal, return early
    if header_component.category == CategoryFlag.HEARTBEAT:
        return await send_heartbeat(header_component, writer, close_conn=header_component.finish)

    # Header verified, process incoming authentication bytes
    auth_component: BaseAuthComponent = await process_auth(header_component.auth_size, reader, writer)
    if not auth_component:
        return
    
    # Authentication bytes semantically valid, perform actual authentication against session data
    ...

async def main() -> None:
    if not response_codes:
        raise RuntimeError('No response codes found, server cannot start...')
    
    session_master: SessionMaster = SessionMaster()
    server: asyncio.Server = await asyncio.start_server(client_connected_cb=partial(callback, session_master=session_master),
                                                        host='127.0.0.1', port=8000)
    async with server:
        await server.serve_forever()

asyncio.run(main())
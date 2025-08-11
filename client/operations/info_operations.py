import asyncio

from client import session_manager
from client.auxillary import operational_utils
from client.config import constants as client_constants
from client.communication import incoming, outgoing
from client.cmd import cmd_utils

from models.request_model import BaseHeaderComponent
from models.flags import CategoryFlag
from models.response_codes import SuccessFlags

async def send_heartbeat(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                         client_config: client_constants.ClientConfig, session_master: session_manager.SessionManager,
                         end_connection: bool = False) -> None:
    
    header_component: BaseHeaderComponent = operational_utils.make_header_component(client_config, session_master, finish=end_connection, category=CategoryFlag.HEARTBEAT, subcategory=1)

    await outgoing.send_request(writer, header_component)

    response_header, _ = await incoming.process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.HEARTBEAT.value:
        await cmd_utils.display('Failed to perform heartbeat')
        return
        # TODO: Add generic message factories
    
    await cmd_utils.display('Doki Doki')
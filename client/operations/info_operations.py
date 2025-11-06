'''Methods corresponding to queries'''

import asyncio

from client import session_manager
from client.auxillary import operational_utils
from client.config import constants as client_constants
from client.communication import incoming, outgoing
from client.cmd import cmd_utils

from models.request_model import BaseHeaderComponent, BaseInfoComponent
from models.flags import CategoryFlag, InfoFlags
from models.response_codes import SuccessFlags
from models.constants import UNAUTHENTICATED_INFO_OPERATIONS

__all__ = ('send_heartbeat', 'send_info_query')

async def send_heartbeat(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                         client_config: client_constants.ClientConfig, session_master: session_manager.SessionManager,
                         end_connection: bool = False) -> None:
    
    header_component: BaseHeaderComponent = operational_utils.make_header_component(client_config, session_master,
                                                                                    finish=end_connection,
                                                                                    category=CategoryFlag.INFO, subcategory=InfoFlags.HEARTBEAT)

    await outgoing.send_request(writer, header_component)

    response_header, _ = await incoming.process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.HEARTBEAT:
        await cmd_utils.display('Failed to perform heartbeat')
        return
        # TODO: Add generic message factories
    
    await cmd_utils.display('Doki Doki')

async def send_info_query(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                          client_config: client_constants.ClientConfig, session_master: session_manager.SessionManager,
                          subcategory_flags: InfoFlags, resource: str,
                          end_connection: bool = False) -> None:
    header_component: BaseHeaderComponent = operational_utils.make_header_component(client_config, session_master, CategoryFlag.INFO, subcategory_flags, finish=end_connection)
    info_component: BaseInfoComponent = BaseInfoComponent(subject_resource=resource)
    extracted_subcategory: InfoFlags = InfoFlags(subcategory_flags & InfoFlags.OPERATION_EXTRACTION_BITS)

    await outgoing.send_request(writer=writer,
                                header_component=header_component,
                                auth_component=None if extracted_subcategory in UNAUTHENTICATED_INFO_OPERATIONS else session_master.auth_component,
                                body_component=info_component)

    response_header, response_body = await incoming.process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_QUERY_ANSWER:
        await cmd_utils.display(f'{response_header.code}: Failed to perform query operation: {extracted_subcategory._name_}')
        return
    
    await cmd_utils.display(cmd_utils.format_dict(response_body.contents)
                            if (response_body and response_body.contents)
                            else f'No available information for operation {extracted_subcategory._name_} on resource {resource}')
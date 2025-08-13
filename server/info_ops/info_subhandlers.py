import asyncio

from models.response_codes import SuccessFlags
from models.response_models import ResponseHeader, ResponseBody
from models.request_model import BaseHeaderComponent

from server.dependencies import ServerSingletonsRegistry

async def handle_heartbeat(header: BaseHeaderComponent, dependency_registry: ServerSingletonsRegistry) -> tuple[ResponseHeader, None]:
    '''Send a heartbeat signal back to the client'''
    return (
        ResponseHeader.from_server(config=dependency_registry.server_config, code=SuccessFlags.HEARTBEAT.value, version=header.version, ended_connection=header.finish),
        None
    )
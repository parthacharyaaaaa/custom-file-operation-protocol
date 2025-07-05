import asyncio
from server.authz.auth_handler import top_auth_handler
from server.comms_utils.outgoing import send_heartbeat
from server.config import CategoryFlag
from server.file_ops.file_handler import top_file_handler
from models.response_models import ResponseHeader, ResponseBody
from models.request_model import BaseHeaderComponent
from server.permission_ops.permission_handler import top_permission_handler
from typing import Any, Coroutine, Optional, Callable
from types import MappingProxyType

TOP_LEVEL_REQUEST_MAPPING: MappingProxyType[int, Callable[[asyncio.StreamReader, BaseHeaderComponent], Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]]] = (
    MappingProxyType({CategoryFlag.AUTH : top_auth_handler,
                      CategoryFlag.HEARTBEAT : send_heartbeat,
                      CategoryFlag.FILE_OP : top_file_handler,
                      CategoryFlag.PERMISSION : top_permission_handler}))
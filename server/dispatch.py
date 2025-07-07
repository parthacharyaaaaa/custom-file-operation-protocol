import asyncio
from typing import Any, Coroutine, Optional, Callable
from types import MappingProxyType

from models.flags import CategoryFlag
from models.response_models import ResponseHeader, ResponseBody
from models.request_model import BaseHeaderComponent

from server.authz.auth_handler import top_auth_handler
from server.comms_utils.outgoing import send_heartbeat
from server.file_ops.file_handler import top_file_handler
from server.permission_ops.permission_handler import top_permission_handler

TOP_LEVEL_REQUEST_MAPPING: MappingProxyType[int, Callable[[asyncio.StreamReader, BaseHeaderComponent], Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]]] = (
    MappingProxyType({CategoryFlag.AUTH : top_auth_handler,
                      CategoryFlag.HEARTBEAT : send_heartbeat,
                      CategoryFlag.FILE_OP : top_file_handler,
                      CategoryFlag.PERMISSION : top_permission_handler}))
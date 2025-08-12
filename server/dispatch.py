import asyncio
from typing import Any, Coroutine, Optional, Callable
from types import MappingProxyType

from models.flags import CategoryFlag
from models.response_models import ResponseHeader, ResponseBody
from models.request_model import BaseHeaderComponent

from server.authz.auth_handler import top_auth_handler
from server.info_ops.info_handler import top_info_handler
from server.dependencies import ServerSingletonsRegistry
from server.file_ops.file_handler import top_file_handler
from server.permission_ops.permission_handler import top_permission_handler

__all__ = ('TOP_LEVEL_REQUEST_MAPPING',)

TOP_LEVEL_REQUEST_MAPPING: MappingProxyType[int, Callable[[asyncio.StreamReader, BaseHeaderComponent, ServerSingletonsRegistry], Coroutine[Any, Any, tuple[ResponseHeader, Optional[ResponseBody]]]]] = (
    MappingProxyType({CategoryFlag.AUTH         : top_auth_handler,
                      CategoryFlag.INFO         : top_info_handler,
                      CategoryFlag.FILE_OP      : top_file_handler,
                      CategoryFlag.PERMISSION   : top_permission_handler}))
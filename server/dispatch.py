from server.config import CategoryFlag
from types import MappingProxyType, FunctionType
from server.authz.auth_handler import auth_handler
from server.file_ops.permission_handler import permission_handler
from server.file_ops.file_handler import file_handler

TOP_LEVEL_REQUEST_MAPPING: MappingProxyType[int, FunctionType] = MappingProxyType({CategoryFlag.AUTH : auth_handler,
                                                                                   CategoryFlag.FILE_OP : file_handler,
                                                                                   CategoryFlag.PERMISSION : permission_handler})
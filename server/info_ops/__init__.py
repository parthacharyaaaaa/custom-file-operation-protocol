'''Package containing logic for handling INFO related operations'''
from typing import Final

from models.flags import InfoFlags

UNAUTHENTICATED_INFO_OPERATIONS: Final[frozenset[InfoFlags]] = frozenset({InfoFlags.HEARTBEAT})
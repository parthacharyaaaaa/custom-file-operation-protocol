'''Utility functions exclusive to INFO operations'''
import re
import os
from datetime import datetime
from typing import Any

from models.constants import REQUEST_CONSTANTS

from server.errors import InvalidBodyValues

def derive_file_identity(identity: str) -> list[str, str]:
    split_args: list[str] = identity.split('/')
    if len(split_args) != 2:
        raise InvalidBodyValues(f'Invalid file identity: {identity}')
    
    # if not re.match(split_args[0], REQUEST_CONSTANTS.auth.username_regex):
    #     raise InvalidBodyValues(f'Invalid username: {split_args[0]}')
    # if not re.match(split_args[1], REQUEST_CONSTANTS.file.filename_regex):
    #     raise InvalidBodyValues(f'Invalid filename: {split_args[1]}')

    return split_args

def get_local_filedata(fpath: os.PathLike) -> dict[str, Any]:
    stat_res: os.stat_result = os.stat(fpath, follow_symlinks=False)
    return {'Most recent change' : datetime.fromtimestamp(stat_res.st_mtime),
            'most recent access' : datetime.fromtimestamp(stat_res.st_atime),
            'most recent metadata change' :  datetime.fromtimestamp(stat_res.st_ctime),
            'file size (bytes)' : stat_res.st_size}
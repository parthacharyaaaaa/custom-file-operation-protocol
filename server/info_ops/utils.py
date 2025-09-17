'''Utility functions exclusive to INFO operations'''
import re
from pathlib import Path
import os
from datetime import datetime
from typing import Any

from server.errors import InvalidBodyValues

def derive_file_identity(identity: str) -> list[str]:
    split_args: list[str] = identity.split('/')
    if len(split_args) != 2:
        raise InvalidBodyValues(f'Invalid file identity: {identity}')
    
    # if not re.match(split_args[0], REQUEST_CONSTANTS.auth.username_regex):
    #     raise InvalidBodyValues(f'Invalid username: {split_args[0]}')
    # if not re.match(split_args[1], REQUEST_CONSTANTS.file.filename_regex):
    #     raise InvalidBodyValues(f'Invalid filename: {split_args[1]}')

    return split_args

def get_local_filedata(fpath: Path) -> dict[str, Any]:
    stat_res: os.stat_result = fpath.stat(follow_symlinks=False)
    return {'Most recent change' : datetime.fromtimestamp(stat_res.st_mtime),
            'most recent access' : datetime.fromtimestamp(stat_res.st_atime),
            'most recent metadata change' :  datetime.fromtimestamp(stat_res.st_ctime),
            'file size (bytes)' : stat_res.st_size}

def get_local_storage_data(root: Path, user: str) -> dict[str, Any]:
    absolute_dirpath: Path = root / user
    storage: int = 0
    file_storage_data: dict[str, int] = {}
    for dir_entry in os.scandir(absolute_dirpath):
        if not dir_entry.is_file():     # This should never happen, but just in case it does
            continue
        file_size: int = dir_entry.stat(follow_symlinks=False).st_size
        storage += file_size
        file_storage_data.update({dir_entry.name : file_size})
    
    return {'storage_used' : storage,
            'files_made' : len(file_storage_data),
            'storage_details' : file_storage_data}
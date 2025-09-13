'''Script for updating storage values in databaase'''

import os
import warnings
from typing import Final, Optional

from dotenv import load_dotenv

import psycopg as pg
from psycopg import sql
from psycopg import conninfo
from psycopg.rows import dict_row

__all__ = ('main',)

def _update_storage_details(directory: os.PathLike[str],
                            user_storage_mapping: dict[str, int],
                            file_storage_mapping: dict[str, dict[str, int]],
                            username: Optional[str] = None) -> None:
    username = username or os.path.basename(directory)
    file_storage_mapping: dict[str, int] = {}
    storage_counter: int = 0
    filecount: int = 0

    for dir_entry in os.scandir(directory):
        if not dir_entry.is_file():
            continue
        file_size: int = dir_entry.stat(follow_symlinks=False).st_size
        storage_counter += file_size
        file_storage_mapping[dir_entry.name] = file_size
        filecount += 1
    
    user_storage_mapping[username] = {'storage_used' : storage_counter, 'filecount' : filecount}
    file_storage_mapping[username] = file_storage_mapping

def main() -> None:
    users_batch_updation_sql: Final[sql.SQL] = sql.SQL('''UPDATE users
                                                       SET file_count = %s, storage_used = %s
                                                       WHERE username = %s;''')
    
    files_batch_updation_sql: Final[sql.SQL] = sql.SQL('''UPDATE files
                                                       SET file_size = %s
                                                       WHERE owner = %s AND filename = %s''')
    
    server_root: Final[os.PathLike[str]] = os.path.dirname(os.path.dirname(__file__))
    loaded: bool = load_dotenv(dotenv_path=os.path.join(server_root, '.env'),
                               override=True, verbose=True)
    if not loaded:
        raise FileNotFoundError
    
    connection: pg.Connection = pg.connect(conninfo=conninfo.make_conninfo(
        user=os.environ['PG_USERNAME'], password=os.environ['PG_PASSWORD'],
        host=os.environ['PG_HOST'], port=os.environ['PG_PORT'], dbname=os.environ['PG_DBNAME'])
        )
    
    files_directory: os.PathLike[str] = os.path.join(server_root, 'files')
    user_storage_mapping: dict[str, dict[str, int]] = {}
    file_storage_mapping: dict[str, dict[str, int]] = {}

    for user_directory in os.scandir(files_directory):
        if not user_directory.is_dir():
            warnings.warn(f'[Integrity] Entry {user_directory.name}, (path: {user_directory.path}) is not a directory.', ResourceWarning)
            continue

        _update_storage_details(user_directory.path, user_storage_mapping, file_storage_mapping)
    
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.executemany(query=users_batch_updation_sql,
                           params_seq=((data['filecount'], data['storage_used'], user) for user, data in user_storage_mapping.items()))
        cursor.executemany(query=files_batch_updation_sql,
                           params_seq=((file_size, user, filename) for user, data in file_storage_mapping.items()
                                       for filename, file_size in data.items()))
    
    connection.commit()

if __name__ == '__main__':
    main()
from typing import Sequence, Optional, Union
from models.response_codes import SuccessFlags, ClientErrorFlags, ServerErrorFlags
from client.cmd.cmd_utils import format_dict
from traceback import format_exception

__all__ = ('successful_file_hide', 'successful_file_publicise', 'successful_granted_role', 'successful_revoked_role', 'successful_ownership_trasnfer', 'failed_permission_operation')

def successful_file_hide(remote_dir: str, remote_file: str, revoked_info: Sequence[dict[str, str]], code: Optional[SuccessFlags]) -> str:
    revoked_info_str: str = '\n- '.join(f"{mapping['grantee']} : {mapping['role']}" for mapping in revoked_info)
    return (
    f'''{code or SuccessFlags.SUCCESSFUL_FILE_HIDE.value}: Hid file {remote_dir}/{remote_file}, all remote users with public read access have had their permissions revoked.
    Revoked data:{revoked_info_str}
    Note that remote users with permissions granted outside of publicity have not been affected'''
    )

def successful_file_publicise(remote_directory: str, remote_file: str, code: Optional[SuccessFlags] = None) -> str:
    return f'{code or SuccessFlags.SUCCESSFUL_FILE_PUBLICISE.value}: Publicised file {remote_directory}/{remote_file}, all remote users now have read access'

def successful_ownership_trasnfer(remote_file: str, remote_directory: str, new_fpath: str, datetime_string: Optional[str] = None, code: Optional[SuccessFlags] = None) -> str:
    f'''{code or SuccessFlags.SUCCESSFUL_OWNERSHIP_TRANSFER.value}: Transferred ownership of file {remote_file} to {remote_directory}. You now have manager rights to this file.
    New Filepath: {new_fpath},
    transferred at: {datetime_string or "N\A"}'''

def successful_revoked_role(remote_directory: str, remote_file: str, revoked_info: dict[str, str], code: Optional[SuccessFlags] = None) -> str:
    revocation_info_string: str = format_dict(revoked_info)
    return (f'''{code or SuccessFlags.SUCCESSFUL_REVOKE.value}: Revoked permission from file {remote_directory}/{remote_file}
            Role info: {revocation_info_string}''')

def successful_granted_role(remote_directory: str, remote_file: str, remote_user: str, permission: str) -> str:
    return f'Granted permission {permission} to user {remote_user} on file {remote_directory}/{remote_file}'

def failed_permission_operation(remote_directory: str, remote_file: str, remote_user: Optional[str] = None, code: Optional[Union[ClientErrorFlags, ServerErrorFlags]] = None, exc: Optional[Exception] = None) -> str:
    return '\n'.join((f'Code: {code or ClientErrorFlags.UNKNOWN_EXCEPTION} Failed to perform permission operation on file {remote_directory}/{remote_file}',
                     f'Concerned user: {remote_user}' if remote_user else '',
                     f'Traceback: {"\n\t".join(format_exception(exc))}' if exc else ''))
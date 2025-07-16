from traceback import format_exception
from typing import Optional, Sequence, Any

from client.cmd.cmd_utils import format_dict

from models.response_codes import SuccessFlags, ClientErrorFlags
from models.flags import FileFlags

__all__ = ('succesful_file_creation', 'succesful_file_deletion', 'successful_file_amendment', 'failed_file_operation',)

def succesful_file_creation(remote_directory: str, remote_file: str, iso_epoch: str, code: Optional[SuccessFlags] = None) -> str:
    return f'Code {code or SuccessFlags.SUCCESSFUL_FILE_CREATION.value}: Created file {remote_directory}/{remote_file} at {iso_epoch}'

def succesful_file_deletion(remote_directory: str, remote_file: str, revoked_info: Sequence[dict[str, Any]], deletion_time_string: Optional[str] = None, code: Optional[SuccessFlags] = None) -> str:
    revocation_info_string: str = '\n---\n'.join(format_dict(i) for i in revoked_info)
    return (f'Code {code or SuccessFlags.SUCCESSFUL_FILE_DELETION}: Deleted file {remote_directory}/{remote_file} at {deletion_time_string or "N\A"}\n{revocation_info_string}')

def successful_file_amendment(remote_directory: str, remote_file: str, code: Optional[SuccessFlags] = None) -> str:
    return f'Code: {code or SuccessFlags.SUCCESSFUL_AMEND.value}: Amended file {remote_directory}/{remote_file}'

def failed_file_operation(remote_directory: str, remote_file: str, operation: FileFlags, code: Optional[SuccessFlags] = None, exc: Optional[Exception] = None) -> str:
    return '\n'.join((f'Code: {code or ClientErrorFlags.UNKNOWN_EXCEPTION.value} Failed to perform operation on file {remote_directory}/{remote_file}',
                      f'Operation: {operation._name_}',
                      f'Traceback: {"\n\t".join(format_exception(exc))}' if exc else ''))
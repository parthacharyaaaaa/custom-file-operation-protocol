from traceback import format_exception_only
from typing import Optional, Sequence

from client.cmd.cmd_utils import format_dict

from models.flags import AuthFlags
from models.response_codes import SuccessFlags

from pydantic import ValidationError

def invalid_user_data(exception: Optional[ValidationError] = None) -> str:
    return ':'.join(['Invalid user data', format_exception_only[exception][0] if exception else ''])

def failed_auth_operation(operation: AuthFlags, code: str) -> str:
    return '\n'.join([f'Code {code}: Failed auth operation',
                      f'Operation: {operation}'])

def filecount_mismatch(reported_fcount: int, actual_fcount: int) -> str:
    return f"Count of deleted files sent by server do not match actual number of deleted filenames sent. Reported: {reported_fcount}, got: {actual_fcount}"

def successful_user_creation(remote_user: str, epoch: Optional[float] = None) -> str:
    return f'Created remote user {remote_user}, at: {epoch or "N\A"}'

def successful_user_deletion(remote_user: str, deleted_count: int, deleted_files: Sequence[str]) -> str:
    return f'Deleted remote user {remote_user}, deleted files: {deleted_count}. Files:\n{"\n".join(deleted_files)}'

def successful_authorization(remote_user: str, code: str = SuccessFlags.SUCCESSFUL_AUTHENTICATION.value) -> str:
    return f'Code {code}: Authorization successful, remote session created with identity {remote_user}'

def session_iteration_mismatch(local_iteration: int, remote_iteration: int) -> str:
    return f'Session iteration number sent by server does not match with local iteration number, overriding local iteration number {local_iteration} to {remote_iteration}'

def successful_reauthorization(remote_user: str, iteration: int, code: str = SuccessFlags.SUCCESSFUL_SESSION_REFRESH.value) -> str:
    return f'Code {code}: Refreshed remote session for user {remote_user}, session iterations: {iteration}'

def successful_logout(remote_user: str, code: str = SuccessFlags.SUCCESSFUL_SESSION_TERMINATION.value, **kwargs) -> str:
    return f'Code: {code}: Terminated remote session for {remote_user}.\n{format_dict(**kwargs)}'

def already_authenticated(remote_user: str) -> str:
    return f'Cannot perform authentication for user {remote_user}, already logged in'

def authentication_required() -> str:
    return f"Cannot perform session termination as session doesn't exist"
from typing import Optional
from models.flags import AuthFlags
from pydantic import ValidationError
from traceback import format_exception_only

def invalid_user_data(exception: Optional[ValidationError] = None) -> str:
    return ':'.join(['Invalid user data', format_exception_only[exception][0] if exception else ''])

def failed_auth_operation(operation: AuthFlags, code: str) -> str:
    return '\n'.join([f'Code {code}: Failed auth operation',
                      f'Operation: {operation}'])
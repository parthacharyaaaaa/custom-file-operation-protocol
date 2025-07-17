from models.flags import AuthFlags

def invalid_user_data() -> str:
    return 'Invalid user data'

def failed_auth_operation(operation: AuthFlags, code: str) -> str:
    return '\n'.join([f'Code {code}: Failed auth operation',
                      f'Operation: {operation}'])
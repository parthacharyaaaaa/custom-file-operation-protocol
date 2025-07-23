from typing import Optional

class CommandException(Exception):
    description: str = 'Invalid command issued'

    def __init__(self, description: Optional[str] = None):
        super().__init__(description or self.__class__.description)


class InvalidAuthenticationState(CommandException):
    description: str = 'Invalid authentication state'
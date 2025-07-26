from typing import Optional

class CommandException(Exception):
    description: str = 'Invalid command issued'

    def __init__(self, description: Optional[str] = None):
        self.description = description or self.__class__.description
        super().__init__()


class InvalidAuthenticationState(CommandException):
    description: str = 'Invalid authentication state'
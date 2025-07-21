class CommandException(Exception):
    description: str = 'Invalid command issued'

    def __init__(self, *args):
        super().__init__(*args)
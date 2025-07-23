from typing import Iterable, Optional

from client.cmd import cmd_utils
import client.cmd.errors as cmd_exc
from client.cmd.commands import AuthCommands, FileCommands
from client.cmd.commands import GeneralModifierCommands

from models.request_model import BaseAuthComponent, BaseFileComponent

async def parse_modifiers(tokens: Iterable[str], *expected_modifiers: GeneralModifierCommands, raise_on_unexpected: bool = True) -> list[bool]:
    '''Parse a given command for any additional modifiers provided at the end
    Args:
        tokens (Iterable[str]): Iterable of tokens to parse for modifiers
        expected_modifiers (GeneralModifierCommands): Modifiers to check for
        raise_on_unexpected (bool): Raise a cmd_exc.CommandException if an unnkown modifier is encountered. If set to False, only a warning is issued
    Raises:
        cmd_exc.CommandException: If raise_on_unexpected is True and an unexpected modifier is found
    Returns:
        tuple[bool]: Boolean values indicating presence/absence of expected modifiers, in same order as passed args
    '''
    warnings: set[str] = set()
    modifiers_found: list[bool] = [False] * len(expected_modifiers)
    #TODO|NOTE: Constructing modifier_map may be overkill if we plan to have < 5 additional modifiers total, as a tuple/list would provide much better perf than a hashed collection 
    modifier_map: dict[str, int] = {modifier.value.upper():i for i, modifier in enumerate(expected_modifiers)}
    for token in tokens:
        if (given_modifier:=token.upper()) in modifier_map:
            modifier_index: int = modifier_map[given_modifier]
            if modifiers_found[modifier_index]: # Repeated
                err_str: str = f'Duplicate modifier {given_modifier} provided, ignoring...'
                warnings.add(err_str)
                continue

            modifiers_found[modifier_index] = True  # Unique
        else:   # Unexpected modifier
            err_str: str = f'Unexpected modifier {given_modifier} provided'
            if raise_on_unexpected:
                raise cmd_exc.CommandException(err_str)
            warnings.add(err_str)
            
    
    await cmd_utils.display(b'\n'.join(warning for warning in warnings))
    
    return modifiers_found

def parse_authorization(tokens: Iterable[str]) -> BaseAuthComponent:
    if len(tokens) < 2:
        raise cmd_exc.CommandException(f'Command {AuthCommands.AUTH} requires username and password to be provided as {AuthCommands.AUTH} USERNAME PASSWORD')
    return BaseAuthComponent(identity=tokens[0], password=tokens[1])

async def parse_auth_modifiers(tokens: Iterable[str]) -> list[bool, bool]:
    '''Abstraction over parse_modifier calls for auth-related operations. Calls parse_modifiers with predetermined expected_modifiers args
    Order of modifiers: `DISPLAY CREDENTIALS`, `END CONNECTION`
    '''
    return await parse_modifiers(tokens, GeneralModifierCommands.DISPLAY_CREDENTIALS.value, GeneralModifierCommands.END_CONNECTION.value)

def parse_file_command(tokens: Iterable[str], operation: FileCommands, default_dir: str, allow_dir: bool = True) -> BaseFileComponent:
    token_length: int = len(tokens)
    if token_length < 1:
        raise cmd_exc.CommandException(f'Command {operation.value} requires filename to be provided')
    
    remote_dir = next(filter(lambda token : token not in GeneralModifierCommands.__members__, tokens[1:]), None) if allow_dir else default_dir
    return BaseFileComponent(subject_file=tokens[0], subject_file_owner=remote_dir)
    
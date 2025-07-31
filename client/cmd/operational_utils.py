from client.cmd.cmd_utils import display
import client.cmd.errors as cmd_errors 

from models.request_model import BaseAuthComponent

import pydantic

async def make_auth_component(username: str, password: str) -> BaseAuthComponent:
    try:
        return BaseAuthComponent(identity=username, password=password)
    except pydantic.ValidationError as v:
        error_string: str = '\n'.join(f'{err_details["loc"][0]} (input={err_details["input"]}): {err_details["msg"]}' for err_details in v.errors())
        raise cmd_errors.CommandException('Invalid login credentials:\n'+error_string)
'''Auxillary functions for client operations'''
from typing import Union
from client.auxillary.typing import SupportsBuffer

def cast_as_memoryview(arg: Union[str, SupportsBuffer]):
    if isinstance(arg, str): return memoryview(arg.encode(encoding='utf-8'))
    return memoryview(arg)

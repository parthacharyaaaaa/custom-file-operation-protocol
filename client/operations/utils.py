'''Auxillary functions for client operations'''
from typing import Union

def cast_as_memoryview(arg: Union[str, bytes, bytearray]):
    if isinstance(arg, str): return memoryview(arg.encode(encoding='utf-8'))
    return memoryview(arg)

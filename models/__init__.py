'''Models and objects shared between server and client'''

from models.constants import load_constants, REQUEST_CONSTANTS, RESPONSE_CONSTANTS
load_constants()
assert REQUEST_CONSTANTS and RESPONSE_CONSTANTS
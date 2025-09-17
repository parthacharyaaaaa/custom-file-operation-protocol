'''Models and objects shared between server and client'''

from models.constants import load_constants
load_constants()
from models.constants import REQUEST_CONSTANTS, RESPONSE_CONSTANTS
assert REQUEST_CONSTANTS and RESPONSE_CONSTANTS
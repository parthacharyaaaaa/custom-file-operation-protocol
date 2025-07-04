'''Server package'''
import os
import yaml
from types import MappingProxyType
from dotenv import load_dotenv

_loaded: bool = load_dotenv(os.path.join(__package__, '.env'))
if not _loaded:
    raise RuntimeError('Failed to load env vars')
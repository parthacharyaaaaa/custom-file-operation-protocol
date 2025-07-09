'''Server package'''
import os
from dotenv import load_dotenv
from server.config.server_config import load_server_config

_loaded: bool = load_dotenv(os.path.join(__package__, '.env'))
if not _loaded:
    raise RuntimeError('Failed to load env vars')

load_server_config()
'''Server package'''
import os
from dotenv import load_dotenv

_loaded: bool = load_dotenv(os.path.join(str(__package__), '.env'))
if not _loaded:
    raise RuntimeError('Failed to load env vars')

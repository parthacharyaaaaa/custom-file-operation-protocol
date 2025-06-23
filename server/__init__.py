'''Server package'''
import os
import yaml
from types import MappingProxyType
from dotenv import load_dotenv

_loaded: bool = load_dotenv(os.path.join(__package__, 'server.env'))
if not _loaded:
    raise RuntimeError('Failed to load env vars')

response_codes: MappingProxyType[str, str] = None

with open(os.path.join(os.path.dirname(__package__), 'responses.yaml')) as responses_file:
    response_codes = MappingProxyType(yaml.load(responses_file.read(), yaml.Loader))
    if not response_codes:
        raise RuntimeError('No response codes found')
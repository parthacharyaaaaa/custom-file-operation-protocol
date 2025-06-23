'''Server package'''
import os
import yaml
from types import MappingProxyType
import sys

response_codes: MappingProxyType[str, str] = None

with open(os.path.join(os.path.dirname(__package__), 'responses.yaml')) as responses_file:
    response_codes = MappingProxyType(yaml.load(responses_file.read(), yaml.Loader))
    if not response_codes:
        raise RuntimeError('No response codes found')
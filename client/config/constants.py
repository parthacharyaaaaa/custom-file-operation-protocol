from pydantic import BaseModel

__all__ = ('ClientConfig', 'CLIENT_CONFIG')

class ClientConfig(BaseModel):
    ...

CLIENT_CONFIG: ClientConfig = None

def initialize_client_configurations() -> ClientConfig:
    ...
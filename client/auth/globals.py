from models.session_metadata import SessionMetadata
from models.request_model import BaseAuthComponent

__all__ = ('current_session_metadata', 'current_auth_component', 'auth_response_schema')

current_session_metadata: SessionMetadata = None
current_auth_component: BaseAuthComponent = None

auth_response_schema: str = None
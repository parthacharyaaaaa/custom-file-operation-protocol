import os
from server.authz.singleton import MetaSessionMaster

class SessionMaster(metaclass=MetaSessionMaster):
    '''Class for managing user sessions'''

    def __init__(self):
        pass

    def authorize_session():
        pass

    def authenticate_session():
        pass

    def terminate_session():
        pass

    def refresh_session():
        pass

    def ban():
        pass
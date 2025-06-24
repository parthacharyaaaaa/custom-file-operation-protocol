import warnings

class MetaSessionMaster(type):
    _instance = None

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instance = super().__call__(*args, **kwargs)
        else:
            warnings.warn(message='Attempted to re-instantiate singleton SessionMaster', category=RuntimeWarning)
        return cls._instance
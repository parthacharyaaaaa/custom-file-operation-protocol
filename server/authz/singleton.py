import warnings

class MetaUserManager(type):
    _instance = None

    def __call__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__call__(*args, **kwargs)
        else:
            warnings.warn(message='Attempted to re-instantiate singleton UserManager', category=RuntimeWarning)
        return cls._instance
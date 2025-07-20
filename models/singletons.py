from typing import Any
import warnings

class SingletonMetaclass(type):
    _instance: Any = None

    def __call__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__call__(*args, **kwargs)
        else:
            warnings.warn('Attempt to instantiate a singleton class more than once, rejecting...', category=RuntimeWarning)
        return cls._instance
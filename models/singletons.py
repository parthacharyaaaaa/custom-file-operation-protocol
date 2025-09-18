'''Singleton metaclass support with runtime enforcement'''
from typing import Any, Optional
import warnings
import weakref

__all__ = 'SingletonMetaclass',

class SingletonMetaclass(type):
    _instance_reference: Optional[weakref.ReferenceType[Any]] = None

    def __call__(cls, *args, **kwargs):
        if not cls._instance_reference:
            # A temporary strong reference is needed for this method's lifetime, 
            # otherwise the object gets garbage collected before being returned to the constructor's assignee
            instance = super().__call__(*args, **kwargs)
            cls._instance_reference = weakref.ref(instance, lambda _ : setattr(cls, "_instance_reference", None))
        else:
            warnings.warn('Attempt to instantiate a singleton class more than once, rejecting...', category=RuntimeWarning)
        
        return cls._instance_reference()

import argparse
from types import SimpleNamespace
import sys

class ExplicitArgumentParser(argparse.ArgumentParser):
    '''Wrapper over argparse.ArgumentParser to allow parsing errors to raise exceptions to be handled explicitly'''
    def parse_known_args(self, args=None, namespace=None):
        if args is None:
            # args default to the system args
            args = sys.argv[1:]
        else:
            # make sure that args are mutable
            args = list(args)

        # default Namespace built from parser defaults
        if namespace is None:
            namespace = argparse.Namespace()

        # add any action defaults that aren't present
        for action in self._actions:
            if action.dest is not argparse.SUPPRESS:
                if not hasattr(namespace, action.dest):
                    if action.default is not argparse.SUPPRESS:
                        setattr(namespace, action.dest, action.default)

        # add any parser defaults that aren't present
        for dest in self._defaults:
            if not hasattr(namespace, dest):
                setattr(namespace, dest, self._defaults[dest])

        # parse the arguments and exit if there are any errors
        if self.exit_on_error:
            namespace, args = self._parse_known_args(args, namespace)
        else:
            namespace, args = self._parse_known_args(args, namespace)

        if hasattr(namespace, argparse._UNRECOGNIZED_ARGS_ATTR):
            args.extend(getattr(namespace, argparse._UNRECOGNIZED_ARGS_ATTR))
            delattr(namespace, argparse._UNRECOGNIZED_ARGS_ATTR)
        return namespace, args
    
    def parse_args(self, args=None, namespace=None):
        '''Parse args (yep)
        
        Raises:
            argparse.ArgumentError: On encountering unknown arguments
            
        Returns:
            (argparse.Namespace) Namespace with known arguments as attributes'''
        args, argv = self.parse_known_args(args, namespace)
        if argv:
            raise argparse.ArgumentError(None, f'unrecognized arguments: {", ".join(argv)}')
        return args
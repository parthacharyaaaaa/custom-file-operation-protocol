'''Wrapper over argparse.ArgumentParser to allow parsing errors to raise exceptions to be handled explicitly'''
import argparse
import sys
import warnings
from typing import Optional, Final, Union

__all__ = ('ExplicitArgumentParser',)

class ExplicitArgumentParser(argparse.ArgumentParser):
    '''Wrapper over argparse.ArgumentParser to allow parsing errors to raise exceptions to be handled explicitly'''
    exclusion_message: Final[str] = 'Note: Argument "{arg}" accepted but not used for this operation.'

    def parse_known_args(self, args=None, namespace=None):  # type: ignore[PylancereportIncompatibleMethodOverride]
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
    
    def parse_args_with_exclusion(self, args=None, namespace=None, exclusion_set: Optional[Union[set[str], frozenset[str]]] = None):
        '''Parse args (yep)
        
        Raises:
            argparse.ArgumentError: On encountering unknown arguments
            
        Returns:
            (argparse.Namespace) Namespace with known arguments as attributes'''
        args, argv = self.parse_known_args(args, namespace)
        if argv:
            raise argparse.ArgumentError(None, f'unrecognized arguments: {", ".join(argv)}')
        
        if exclusion_set:
            display_strings: tuple[str, ...] = tuple(ExplicitArgumentParser.exclusion_message.format(arg=excluded_arg)
                                                     for excluded_arg in 
                                                     exclusion_set.intersection(set(key
                                                                                    for key, value in args.__dict__.items() if value is not None)))
            if display_strings:
                print(*display_strings, sep='\n')
        return args
    
    def inject_default_argument(self, positional_argument: str, **action_kw) -> None:
        target_action: argparse.Action = next(filter(lambda action : action.dest == positional_argument, self._actions))
        for attr_name, attr_value in action_kw.items():
            if not hasattr(target_action, attr_name):
                warnings.warn(f'Argument parser {self} has no attribute: {attr_name}')
                continue
            setattr(target_action, attr_name, attr_value)

    def error(self, message):       # type: ignore[PylancereportIncompatibleMethodOverride]
        self.print_usage(sys.stderr)

    def exit(self, status=0, message=None) -> None: # type: ignore[PylancereportIncompatibleMethodOverride]
        if message:
            self._print_message(message, sys.stderr)
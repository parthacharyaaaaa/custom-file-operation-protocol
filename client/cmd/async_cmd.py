import argparse
import cmd
import inspect
from traceback import format_exc, format_exception_only

from client.cmd import cmd_utils
from client.cmd import errors as cmd_errors

import pydantic

class AsyncCmd(cmd.Cmd):
    def parseline(self, line: str):
        line = line.strip()
        if not line:
            return None, None, line
        elif line[0] == '?':
            line = 'help ' + line[1:]
        elif line[0] == '!':
            if hasattr(self, 'do_shell'):
                line = 'shell ' + line[1:]
            else:
                return None, None, line
        i, n = 0, len(line)
        while i < n and line[i] in self.identchars: i = i+1
        cmd, arg = line[:i].lower(), line[i:].strip()
        return cmd, arg, line

    def default(self, line):
        self.stdout.write(f'UNKNOWN COMMAND: {line.split()[0]}\n')
        self.do_help(None)

    async def postcmd(self, stop, line):
        if self.connection_ended:
            self.writer.close()
            await self.writer.wait_closed()

            if self.session_master.identity:
                self.session_master.clear_auth_data()
            
            return True

    async def cmdloop(self, intro = None):
        self.preloop()
        if self.use_rawinput and self.completekey:
            try:
                import readline
                self.old_completer = readline.get_completer()
                readline.set_completer(self.complete)
                readline.parse_and_bind(self.completekey+": complete")
            except ImportError:
                pass
        try:
            if intro is not None:
                self.intro = intro
            if self.intro:
                self.stdout.write(str(self.intro)+"\n")
            stop = None
            while not stop:
                if self.cmdqueue:
                    line = self.cmdqueue.pop(0)
                else:
                    if self.use_rawinput:
                        try:
                            line = input(self.prompt)
                        except EOFError:
                            line = 'EOF'
                    else:
                        self.stdout.write(self.prompt)
                        self.stdout.flush()
                        line = self.stdin.readline()
                        if not len(line):
                            line = 'EOF'
                        else:
                            line = line.rstrip('\r\n')
                line = self.precmd(line)
                stop = await self.onecmd(line)
                stop = await self.postcmd(stop, line)
            self.postloop()
        finally:
            if self.use_rawinput and self.completekey:
                try:
                    import readline
                    readline.set_completer(self.old_completer)
                except ImportError:
                    pass

    async def onecmd(self, line):
        cmd, arg, line = self.parseline(line)
        if not line:
            return self.emptyline()
        if cmd is None:
            return self.default(line)
        self.lastcmd = line
        if line == 'EOF' :
            self.lastcmd = ''
        if cmd == '':
            return self.default(line)
        else:
            try:
                func = getattr(self, 'do_' + cmd)
            except AttributeError:
                return self.default(line)
            
            # Additional logic added here to deal with any asynchronous functions
            try:
                if inspect.iscoroutinefunction(inspect.unwrap(func)):
                    return await func(arg)
                else:
                    return func(arg)
            except cmd_errors.CommandException as cmd_exc:
                await cmd_utils.display(cmd_exc.description)
            except (argparse.ArgumentError, argparse.ArgumentTypeError) as arg_exc:
                await cmd_utils.display(getattr(arg_exc, 'message', format_exception_only(arg_exc)[0]))
            except pydantic.ValidationError as v:
                error_string: str = '\n'.join(f'{err_details["loc"][0]} (input={err_details["input"]}): {err_details["msg"]}' for err_details in v.errors())
                await cmd_utils.display(error_string)
            except Exception as e:
                await cmd_utils.display(format_exc())

            
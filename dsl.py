import logging
import shutil
import pwd
import os
import sys
from pathlib import Path
import dsl_stdlib

logger = logging.getLogger(__name__)


class DslException(Exception):
    pass


class Ctx:
    def __init__(self,
                 is_loud: bool = True,
                 halt_on_error: bool = False,
                 src: str = "<inline>",
                 args: list = ["__main__"],
                 log_stderr: bool = True,
                 log_stdout: bool = True,
                 dry_run: bool = False,
                 cwd: Path = Path.cwd(),
                 config: dict = None,
                 is_inline: bool = False,
                 recursion_depth: int = 0,
                 scope: list[dict] = None,
                 ):

        # TODO: make logging output to log facilities too
        def cprint(x):
            nonlocal src, is_loud
            if is_loud:
                logging.info("%s: %s", src, x.replace("\n", '\u23ce'))

        self.config = config
        self.args = args
        self.log_stderr = cprint if log_stderr else Ctx.__dummy_log
        self.log_stdout = cprint if log_stdout else Ctx.__dummy_log
        self.src = src
        self.recursion_depth = recursion_depth
        self.halt_on_error = halt_on_error
        self.dry_run = dry_run
        self.cwd = cwd
        self.scope = Ctx.get_empty_scope(config) if scope is None else scope
        self.is_loud = is_loud
        self.is_inline = is_inline

        if not is_inline and config is None:
            error_dsl(
                self,
                "Tried to make a non-inline context without a reference to a config file. src: %s" % src,
                True
            )

    @staticmethod
    def get_empty_scope(config) -> list[dict]:
        # TODO: add all global scope items
        return [{
            "arch": os.uname().machine,
            "py_exec": sys.executable,
            "shell_path": pwd.getpwuid(os.getuid()).pw_shell or shutil.which("bash") or shutil.which("sh")
        }, {}]

    @staticmethod
    def from_config(config: dict, src: str, working_directory: Path):
        src = config["command"].upper() + " " + src
        ctx = Ctx(
            is_loud=config["is_loud"],
            halt_on_error=config["halt_on_error"], src=src, args=["__main__"],
            log_stderr=True, log_stdout=True, dry_run=config["dry_run"],
            cwd=working_directory, config=config, is_inline=False,
            recursion_depth=0, scope=None
        )
        return ctx

    def recurse(self, call: list):
        # args = call[1:]
        src = self.src + " => %s" % call[0]
        log_stdout = self.log_stdout
        if self.recursion_depth == 10:
            self.log_stdout("Recursion depth exceeded stdout limit, suppressing stdout")
            log_stdout = Ctx.__dummy_log
        if self.recursion_depth > 1024:
            error_dsl(self, "Exceeded recursion limit!", True)

        return Ctx(
            is_loud=self.is_loud,
            halt_on_error=self.halt_on_error, src=src, args=self.args,
            log_stderr=self.log_stderr, log_stdout=log_stdout,
            dry_run=self.dry_run, cwd=self.cwd, config=self.config,
            is_inline=self.is_inline, recursion_depth=self.recursion_depth+1,
            scope=self.scope+[{}]
        )

    def query_scope(self, name: str, reverse=False) -> str:
        r = range(len(self.scope))
        if not reverse:
            r = r[::-1]

        for i in r:
            if name in self.scope[i]:
                return self.scope[i][name]

        return None

    @staticmethod
    def __dummy_log(log):
        pass


def error_dsl(ctx, msg, panic=False):
    logging.error(msg)
    logging.error("Trace: %s", ctx.src)
    if ctx.halt_on_error or panic:
        raise DslException(msg)


async def run_commands(config, commands, src, working_directory):
    logging.debug("Running command %s", repr(commands))
    ctx = Ctx.from_config(config, src, working_directory)

    await eval_value_dsl(ctx, commands)


async def eval_value_dsl(ctx, value):
    # evaluate context concatenation
    if type(value) is dict:
        return ctx.args

    # evaluate literals
    elif type(value) is str:
        return [value]

    # evaluate nested calls
    elif type(value) is list:
        newctx = Ctx.recurse(ctx, value)
        out = await eval_command_dsl(newctx, value[0], value[1:])
        return out

    # evaluate an index into the context
    elif type(value) is float or type(value) is int:
        value = int(value) - 1  # indexes are from 1
        if 0 <= value < len(ctx.args):
            return [ctx.args[value]]
        error_dsl(ctx, "Tried to index argument #%d. Only %d arguments were given: %s" % (value, len(ctx.args), repr(ctx.args)))
        return [""]

    # invalid value
    else:
        error_dsl(ctx, "Tried to evaluate invalid value %s" % repr(value))
        return [""]


async def eval_command_dsl(ctx, command, call_args):
    # handle special commands:
    # no-op command
    if len(command) == 0:
        return []

    cmd = command
    args = []

    # Evaluate all arguments
    for i in call_args:
        args += await eval_value_dsl(ctx, i)

    logger.debug("Evaluated arguments %s to %s", repr(call_args), args)
    ctx.args = args

    # run the command
    # check stdlib for command first
    result = await dsl_stdlib.run_stdlib_func(ctx, cmd, args)
    if result is not None:
        return result

    # check libraries for command
    if cmd in ctx.config["lib"]:
        return await eval_value_dsl(ctx, ctx.config["lib"][cmd]["body"])

    # didnt find command!
    error_dsl(ctx, "Tried to invoke nonexistent command %s" % cmd)
    return []


def normalise_dsl(command, ctx=None, src=None):
    if ctx is None:
        ctx = Ctx(is_inline=True, src=src)
        result = normalise_dsl(command, ctx, src)
        logging.debug("Normalised DSL %s into %s", command, result)
        return result
    # a concatenation command
    if type(command) is list:
        if len(command) == 0:
            return []

        return ["cat"] + [normalise_dsl(i, ctx, src) for i in command]
    # calls, or special commands
    elif type(command) is dict:
        # special context expand
        if len(command) == 0:
            return {}
        # a regular call
        elif len(command) == 1:
            cmd = [*command][0]
            args = command[cmd]
            if type(args) is str:
                args = [args]
            else:
                args = [normalise_dsl(i, ctx, src) for i in args]
            return [cmd]+args
        else:
            error_dsl(ctx, "DSL call included more than one function", True)
    # argument indexes
    elif type(command) is int:
        return command
    # literals (?)
    elif type(command) is str:
        return command
    # unknown type
    else:
        error_dsl(ctx, "Unexpected type %s in command: %s" % (type(command), repr(command)), True)

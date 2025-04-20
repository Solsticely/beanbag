import logging
import shutil
import pwd
import os
import sys
from pathlib import Path
import dsl_stdlib
import tomllib

logger = logging.getLogger(__name__)


class DslException(Exception):
    pass


class Ctx:
    def __init__(self, *,
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
            self.error(
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

    # def recurse(self, call: DslCall):
    def recurse(self, call, args):
        # args = call[1:]
        src = self.src + " => %s" % call.cmd
        # src = self.src + " => %s" % repr(call)
        log_stdout = self.log_stdout
        if self.recursion_depth == 10:
            self.log_stdout("Recursion depth exceeded stdout limit, suppressing stdout")
            log_stdout = Ctx.__dummy_log
        if self.recursion_depth > 1024:
            self.error("Exceeded recursion limit!", True)

        return Ctx(
            is_loud=self.is_loud,
            halt_on_error=self.halt_on_error, src=src, args=args,
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

    def error(self, msg: str, panic=False):
        logging.error("Trace: %s", self.src)
        logging.error(msg)

        if self.halt_on_error or panic:
            raise DslException(msg)

    @staticmethod
    def __dummy_log(log):
        pass


class DslExpr:
    """
    A generic class for all DSL expressions
    """

    async def evaluate(self, ctx: Ctx) -> list[str]:
        return []

    def __repr__(self) -> str:
        return "[]"

    def __init__(self, ctx: Ctx):
        pass


class DslNoop(DslExpr):
    """
    A DSL noop command, represented in TOML with an empty array.
    """


class DslArgumentExpansion(DslExpr):
    """
    A DSL argument expansion expression, represented in TOML with an empty
    dictionary.

    Is replaced with all of the arguments to the function being called. None of
    the arguments are concatenated and are instead each their own item
    """
    async def evaluate(self, ctx: Ctx) -> list[str]:
        return ctx.args

    def __repr__(self) -> str:
        return "$@"


class DslLiteral(DslExpr):
    """
    A DSL string literal
    """

    def __init__(self, ctx: Ctx, value: str):
        super().__init__(ctx)
        self.value = value

    async def evaluate(self, ctx: Ctx) -> list[str]:
        return [self.value]

    def __repr__(self) -> str:
        return "$"+repr(self.value)


class DslArgIndex(DslExpr):
    """
    A DSL args array index. Represented in TOML with a number.

    Evaluates to the n-th argument of the calling function.
    """

    def __init__(self, ctx: Ctx, inx: int):
        super().__init__(ctx)
        inx = int(inx)
        if inx < 1:
            if inx == 0:
                logger.error(
                    "Argument indexes are 1-indexed. Did you mean to use 1 instead?"
                )
            ctx.error("Argument index %d smaller than 1" % inx, True)
        self.inx = inx

    async def evaluate(self, ctx: Ctx) -> list[str]:
        if len(ctx.args) >= self.inx:
            return [ctx.args[self.inx-1]]

        ctx.error(
            "Tried to index argument #%d. Only %d arguments were given: %s" %
            (self.inx, len(ctx.args), repr(ctx.args))
        )
        return [""]

    def __repr__(self) -> str:
        return "{}"


class DslCall(DslExpr):
    """
    A DSL function call. Represented in TOML with a dictionary with one item.
    The key represents the name of the function being called, and the value
    represents the call arguments.
    """

    def __init__(self, ctx: Ctx, cmd: str, args: list[DslExpr]):
        super().__init__(ctx)
        self.cmd = cmd
        self.args = args

    async def evaluate(self, ctx: Ctx) -> list[str]:
        # Evaluate args
        eval_args = [j for i in self.args for j in await i.evaluate(ctx)]
        logger.debug("Evaluated call arguments %s to %s", repr(self.args), eval_args)
        newctx = ctx.recurse(self, eval_args)

        # run the command
        # check stdlib for command first
        result = await dsl_stdlib.run_stdlib_func(newctx, self.cmd, eval_args)
        if result is not None:
            return result

        # check libraries for command
        if self.cmd in ctx.config["lib"]:
            return await ctx.config["lib"][self.cmd]["body"].evaluate(newctx)

        # didnt find command!
        ctx.error("Tried to invoke nonexistent command %s" % self.cmd)
        return [""]

    def __repr__(self) -> str:
        return "%s(%s)" % (self.cmd, ", ".join([repr(i) for i in self.args]))


async def run_commands(config, command, src, working_directory):
    logging.debug("Running command %s", repr(command))
    ctx = Ctx.from_config(config, src, working_directory)

    await command.evaluate(ctx)


def parse_dsl(command, *, src=None, ctx=None) -> DslExpr:
    # If called nonrecursively, debug the results
    if ctx is None:
        ctx = Ctx(is_inline=True, src=src)
        result = parse_dsl(command, ctx=ctx, src=src)
        logging.debug("Normalised DSL %s into %s", command, result)
        return result

    # a concatenation command
    if type(command) is list:
        return DslCall(ctx, "cat", [parse_dsl(i, ctx=ctx, src=src) for i in command])

    # calls, or special commands
    elif type(command) is dict:
        # special context expand
        if len(command) == 0:
            return DslArgumentExpansion(ctx)
        # a regular call
        elif len(command) == 1:
            cmd = [*command][0]
            args = command[cmd]
            if type(args) is str:
                args = [DslLiteral(ctx, args)]
            else:
                args = [parse_dsl(i, ctx=ctx, src=src) for i in args]
            return DslCall(ctx, cmd, args)
        # TODO: implement IF calls
        else:
            ctx.error("DSL call included more than one function", True)
    # argument indexes
    elif type(command) is int:
        return DslArgIndex(ctx, command)
    # literals (?)
    elif type(command) is str:
        return DslLiteral(ctx, command)
    # unknown type
    else:
        ctx.error("Unexpected type %s in command: %s" % (type(command), repr(command)), True)

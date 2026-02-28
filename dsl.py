import shutil
import pwd
import os
import sys
from pathlib import Path
import dsl_stdlib
import security
import printutils

import logging as i_am_intentionally_using_logging_instead_of_logger
logger = i_am_intentionally_using_logging_instead_of_logger.getLogger(__name__)


DIAGNOSIS_LOG_LENGTH = 4096


class DslException(Exception):
    pass


class Ctx:
    def __init__(self, *,
                 is_loud: bool = True,
                 halt_on_error: bool = False,
                 src: str = "<inline>",
                 args: list = ["__main__"],
                 can_log_err: bool = True,
                 can_log_out: bool = True,
                 dry_run: bool = False,
                 cwd: Path = Path.cwd(),
                 config: dict = None,
                 is_inline: bool = False,
                 recursion_depth: int = 0,
                 scope: list[dict] = None,
                 extra_output: list[list[str]] = None,
                 env_vars: dict[str, str] = {},
                 log_file=None,
                 ):

        extra_output = [[""]] if extra_output is None else extra_output
        self.extra_output = extra_output

        self.config = config
        self.args = args
        self.can_log_err = can_log_err
        self.can_log_out = can_log_out
        self.src = src
        self.recursion_depth = recursion_depth
        self.halt_on_error = halt_on_error
        self.dry_run = dry_run
        self.cwd = cwd
        self.scope = Ctx.get_empty_scope(config) if scope is None else scope
        self.is_loud = is_loud
        self.is_inline = is_inline
        self.env_vars = env_vars
        self.log_file = log_file

        if not is_inline and config is None:
            self.error(
                "Tried to make a non-inline context without a reference to a config file. src: %s" % src,
                True
            )

    def log_stderr(self, log):
        self.__generic_log(self.can_log_err, log)

    def log_stdout(self, log):
        self.__generic_log(self.can_log_out, log)

    @staticmethod
    def get_empty_scope(config) -> list[dict]:
        # TODO: add all global scope items
        ARCH_REGEXES = {
            "x86_64": r"(amd64|x86[-_\s]64)",  # TODO: add more arch names
        }
        machine = os.uname().machine
        return [{
            "arch": machine,
            "arch_names": ARCH_REGEXES.get(machine) or machine,
            "py_exec": sys.executable,
            "shell_path": pwd.getpwuid(os.getuid()).pw_shell or shutil.which("bash") or shutil.which("sh")
        }, {}]

    @staticmethod
    def from_config(config: dict, src: str, working_directory: Path, env: dict[str, str], log_file):
        src = config.command.upper() + " " + src
        ctx = Ctx(
            is_loud=config.is_loud,
            halt_on_error=config.halt_on_error, src=src, args=["__main__"],
            can_log_err=True, can_log_out=True, dry_run=config.dry_run,
            cwd=working_directory, config=config, is_inline=False,
            recursion_depth=0, scope=None, extra_output=[[""]], env_vars = env,
            log_file=log_file
        )
        return ctx

    # def recurse(self, call: DslCall):
    def recurse(self, call, args):
        # args = call[1:]
        src = self.src + " \u2192 %s" % call.cmd
        # src = self.src + " => %s" % repr(call)
        can_log_out = self.can_log_out
        # if self.recursion_depth == 10:
        #     logger.warn("Recursion depth exceeded stdout limit, suppressing tty output for STDOUT")
        #     can_log_out = False

        if self.recursion_depth > 1024:
            self.error("Exceeded recursion limit!", True)

        return Ctx(
            is_loud=self.is_loud,
            halt_on_error=self.halt_on_error, src=src, args=args,
            can_log_err=self.can_log_err, can_log_out=can_log_out,
            dry_run=self.dry_run, cwd=self.cwd, config=self.config,
            is_inline=self.is_inline, recursion_depth=self.recursion_depth+1,
            scope=self.scope+[{}], extra_output=self.extra_output,
            env_vars=self.env_vars, log_file=self.log_file
        )

    def query_scope(self, name: str, reverse=False) -> str:
        r = range(len(self.scope))
        if not reverse:
            r = r[::-1]

        for i in r:
            if name in self.scope[i]:
                return self.scope[i][name]

        if name in self.env_vars:
            return self.env_vars[name]

        return None

    def error(self, msg: str, panic=False):
        log_level = logger.critical if self.halt_on_error or panic else logger.error
        log_level("Trace: %s", self.src)
        log_level(msg)

        if self.halt_on_error or panic or self.config.show_log_on_err:
            logger.critical("STDOUT+ERR: %s", self.extra_output[0][0])
            self.extra_output[0][0] = ""
            raise DslException(msg)

        elif len(self.extra_output[0][0].strip()) != 0:
            # TODO: implement --show-log-on-error
            logger.error("use --show-log-on-error to show extra output")

    # TODO: make logging output to config-defined log facilities too
    def __generic_log(self, condition: bool, log: str):
        self.extra_output[0][0] += log
        self.extra_output = self.extra_output[max(0, len(self.extra_output)-DIAGNOSIS_LOG_LENGTH):]

        if condition:
            self.log_file.write(log)
            self.log_file.flush()
        log = log.strip()
        if condition and self.is_loud and len(log) != 0:
            logger.info("%s: %s", self.src, printutils.shrink_lines(log))


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
        return repr(self.value)


class DslIdempotencyCheck(DslExpr):
    """
    A DSL idempotency check, to avoid running a certain piece of code if a file
    already exists. Represented in TOML like
    `{ if_not_exists = "<PATH>", then = <INNER>, else = <OTHERWISE> }`.
    """

    def __init__(self, ctx: Ctx, path: Path, inner: DslExpr, otherwise: DslExpr):
        super().__init__(ctx)
        self.path = path
        self.inner = inner
        self.otherwise = otherwise

    async def evaluate(self, ctx: Ctx) -> list[str]:
        path = security.authorise_workdir_path(ctx, self.path)
        branch = self.otherwise if path.exists() else self.inner
        return await branch.evaluate(ctx)

    def __repr__(self) -> str:
        return '(if !exists(%s): %s; else: %s)' % (
            self.path,
            repr(self.inner),
            repr(self.otherwise)
        )


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
                logger.info(
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
        # dont log STDOUT to TTY if its explicitly asked for
        can_log_out = ctx.can_log_out
        if self.cmd in {"set", "no_tty_log"} and can_log_out:
            logger.warn("Explicitly suppressing TTY output for %s", ctx.src)
            ctx.can_log_out = False

        # Evaluate args
        eval_args = [j for i in self.args for j in await i.evaluate(ctx)]

        # restore stdout
        ctx.can_log_out = can_log_out

        # logger.debug("Evaluated call arguments %s to %s", repr(self.args), eval_args)
        newctx = ctx.recurse(self, eval_args)

        # run the command
        # check stdlib for command first
        result = await dsl_stdlib.run_stdlib_func(newctx, self.cmd, eval_args)
        if result is not None:
            return result

        # check addons for command
        if self.cmd in ctx.config.lib:
            return await ctx.config.lib[self.cmd].body.evaluate(newctx)

        # didnt find command!
        ctx.error("Tried to invoke nonexistent command %s" % self.cmd)
        return [""]

    def __repr__(self) -> str:
        return "%s(%s)" % (self.cmd, ", ".join([repr(i) for i in self.args]))


async def run_commands(config, service, command, log_file, working_directory: Path | None = None, extra_envs: list[dict[str, str]] = []):
    working_directory = security.workdir(config, service) if working_directory is None else working_directory
    cmd, env = command.cmd, command.env

    # setup environment variables
    env = [config.services[service].env] + extra_envs + [env]
    merged_env = {}
    for scope in env:
        for k, v in scope.items():
            merged_env[k] = v

    logger.debug("Running command %s", repr(cmd))
    ctx = Ctx.from_config(config, service, working_directory, merged_env, log_file)

    await cmd.evaluate(ctx)


def parse_dsl(command, *, src=None, ctx=None) -> DslExpr:
    # If called nonrecursively, debug the results
    if ctx is None:
        ctx = Ctx(is_inline=True, src=src)
        result = parse_dsl(command, ctx=ctx, src=src)
        # logger.debug("Normalised DSL %s into %s", command, result)
        return result

    # a concatenation command
    if isinstance(command, list):
        return DslCall(ctx, "cat", [parse_dsl(i, ctx=ctx, src=src) for i in command])

    # calls, or special commands
    elif isinstance(command, dict):
        keys = [*command]
        # special context expand
        if len(keys) == 0:
            return DslArgumentExpansion(ctx)
        # a regular call
        elif len(keys) == 1:
            cmd = keys[0]
            args = command[cmd]
            if type(args) is list:
                args = [parse_dsl(i, ctx=ctx, src=src) for i in args]
            else:
                args = [parse_dsl(args, ctx=ctx, src=src)]
            return DslCall(ctx, cmd, args)
        elif "if_not_exists" in keys:
            keys = {*keys}

            # do parameter checks
            extra = keys - {"if_not_exists", "then", "else"}
            if len(extra) != 0:
                ctx.error("Extra keys: %s" % extra, True)

            # get parameters
            path = Path(command["if_not_exists"])
            
            inner = command.get("then")
            inner = DslNoop(ctx) if inner is None else parse_dsl(inner, src=src, ctx=ctx)
            
            otherwise = command.get("else")
            otherwise = DslNoop(ctx) if otherwise is None else parse_dsl(otherwise, src=src, ctx=ctx)
            
            return DslIdempotencyCheck(ctx, path, inner, otherwise)
        else:
            ctx.error("Did not recognise special DSL call with arguments {}" % keys, True)
    # argument indexes
    elif isinstance(command, int):
        return DslArgIndex(ctx, command)
    # literals
    elif isinstance(command, str):
        return DslLiteral(ctx, command)
    # unknown type
    else:
        ctx.error("Unexpected type %s in command: %s" % (type(command), repr(command)), True)

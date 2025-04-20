import shutil
import shlex
import asyncio
import json
import random
from pathlib import Path
import printutils
import security
import os

import logging as i_am_intentionally_using_logging_instead_of_logger
logger = i_am_intentionally_using_logging_instead_of_logger.getLogger(__name__)


def checkargs(ctx, args: list[str], minim: int, maxim: int, mode: str = "default", *, default = ""):
    argc = len(args)

    if maxim is None:
        maxim = argc

    assert mode in {"panic", "default", "noneret"}

    panic = mode == "panic"

    if argc < minim:
        ctx.error("expected atleast %d arguments, got %d: %s" % (minim, argc, args), panic)
    if argc > maxim:
        ctx.error("expected at most %d arguments, got %d: %s" % (maxim, argc, args), panic)

    if not (minim <= argc <= maxim) and mode == "noneret":
        return None

    if type(default) is str:
        default = [default] * minim

    return args[:min(argc, maxim)] + default[argc:max(0, minim-argc+1)]


def get_from_scope(ctx, args: list[str], reverse: bool):
    args = checkargs(ctx, args, 1, 1, default="NONEX")
    val = ctx.query_scope(args[0], reverse)
    if val is None:
        ctx.error("Variable %s is not defined" % args[0])
        return ["$%s=UNDEFINED" % args[0]]
    # logger.debug("Getting variable %s: %s", args[0], printutils.clean(val))
    return [val]


def set_to_scope(ctx, args, reverse: bool):
    args = checkargs(ctx, args, 2, 2, "noneret")
    if args is None:
        return [""]
    ctx.scope[1 if reverse else -2][args[0]] = args[1]
    # logger.debug("Setting variable %s: %s", args[0], printutils.clean(args[1]))
    return [args[1]]


class DslStdlib:
    @staticmethod
    async def get(ctx, args):
        return get_from_scope(ctx, args, False)

    @staticmethod
    async def get_global(ctx, args):
        return get_from_scope(ctx, args, True)

    @staticmethod
    async def set(ctx, args):
        return set_to_scope(ctx, args, False)

    @staticmethod
    async def set_global(ctx, args):
        return set_to_scope(ctx, args, True)

    @staticmethod
    async def echo(ctx, args):
        log = await DslStdlib.cat(ctx, args)
        ctx.log_stderr(log[0])
        return [""]

    @staticmethod
    async def no_tty_log(ctx, args):
        return await DslStdlib.cat(ctx, args)

    @staticmethod
    async def cat(ctx, args):
        return ["".join(args)]

    @staticmethod
    async def shquote(ctx, args):
        return [shlex.join(args)]

    @staticmethod
    async def jsonquote(ctx, args):
        if len(args) == 1:
            return [json.dumps(args[0])]
        else:
            return [json.dumps(args)]

    @staticmethod
    async def jsonunquote(ctx, args):
        out = ""
        for i in args:
            try:
                parsed = json.loads(i)
            except json.JSONDecodeError:
                ctx.error("Invalid json payload %s" % i)
                continue
            if type(parsed) is not str:
                ctx.error("Non-string object passed to jsonunquote: %s" % i)
                continue
            out += parsed
        return [out]

    @staticmethod
    async def firstline(ctx, args):
        args = checkargs(ctx, args, 1, 1)[0]
        return [args.partition('\n')[0]]

    @staticmethod
    async def assert_neq(ctx, args):
        args = checkargs(ctx, args, 2, 3, "panic")
        if args[0] == args[1]:
            ctx.error("Assertion failed: %s != %s%s" % (
                repr(args[0]),
                repr(args[1]),
                "" if len(args) == 2 else args[3]
            ), True)
        return [""]

    @staticmethod
    async def randomstr(ctx, args):
        size = checkargs(ctx, args, 1, 1, default="40")[0]
        try:
            size = round(float(size))
        except ValueError:
            ctx.error("Randomstr called with an invalid integer literal")
            size = 40
        if size < 1:
            ctx.error("Cannot generate a random string with %d characters", size)

        ALPHA = "abcdefghijklmnopqrstuvwxyz"
        ALPHA = ALPHA + ALPHA.upper()
        ALNUM = ALPHA + "0123456789"
        result = random.sample(ALPHA, 1) + random.sample(ALNUM, size-1)
        return ["".join(result)]

    @staticmethod
    async def exec(ctx, args):
        args = checkargs(ctx, args, 1, None, "noneret")
        if args is None:
            return [""]

        # find executable
        exec_path = shutil.which(args[0]) or security.authorise_workdir_path(ctx, Path(args[0]), soft=True)
        if type(exec_path) is str:
            exec_path = Path(exec_path)
        if exec_path is None or not exec_path.exists():
            ctx.error("could not find executable %s" % args[0])
            return []
        if not (exec_path.stat().st_mode & os.X_OK):
            ctx.error("Found executable %s is not marked executable. Did you forget a chmod command in your provision script?" % args[0])
            return []
        args[0] = str(exec_path.resolve())

        if ctx.dry_run:
            logger.info("DRY RUN: Running %s", " ".join(args))
            return ["<DRY RUN - COMMAND NOT EXECUTED>"]

        # log redirection & capture
        stringified = printutils.shrink_lines(printutils.truncate(shlex.join(args)))
        # logger.debug("Invoking %s", stringified)

        stdout = ""
        max_len = ctx.config.max_value_len

        async def push_log(stream, log_func, store_output):
            nonlocal stdout
            while not stream.at_eof():
                read = await stream.readline()
                # im crossing my fingers and hoping that this is a good
                # delimiter so we don't break utf-8 continuity!
                read = read.decode("utf-8", "replace")
                log_func(read)
                if store_output:
                    stdout += read[:max(0, max_len - len(stdout))]

        # process creation
        process = await asyncio.create_subprocess_exec(
            args[0], *args[1:],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
            limit=max_len,
            cwd=ctx.cwd
        )
        log_out = push_log(process.stdout, ctx.log_stdout, True)
        log_err = push_log(process.stderr, ctx.log_stderr, False)
        await asyncio.gather(log_out, log_err)

        # The streams are closed after this gather; therefore there isn't a
        # chance of i/o deadlock when we wait here
        await process.wait()

        if process.returncode != 0:
            ctx.error("Process %s exited with exitcode %s!" % (
                shlex.join(args),
                process.returncode
            ))

        return [stdout]


async def run_stdlib_func(ctx, cmd, args):
    if not hasattr(DslStdlib, cmd):
        return None
    result = await getattr(DslStdlib, cmd)(ctx, args)

    if result is None:
        ctx.error("builtin DSL function {} did not return a result!")
        return [""]
    elif type(result) is str:
        ctx.error("DSL function returned an unwrapped string!")
        return [result]
    elif type(result) is not list:
        ctx.error("DSL function returned a non-list result!")
        return [""]

    return result

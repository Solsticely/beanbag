import dsl as bb_dsl
import shutil
import logging
import shlex
import asyncio

logger = logging.getLogger(__name__)


def get_from_scope(ctx, args: list[str], reverse: bool):
    if len(args) != 1:
        ctx.error("get called with more/less than 1 argument")
    vname = "NONEX" if len(args) < 1 else args[0]
    val = ctx.query_scope(vname, reverse)
    if val is None:
        ctx.error("Variable %s is not defined" % vname)
        return ["VARIABLE_%s <does not exist>" % vname]
    return [val]

def set_to_scope(ctx, args, reverse: bool):
    if len(args) != 2:
        ctx.error("set called with more/less than 2 arguments")
        return ["VARIABLE_NONEX"]
    vname = args[0]
    val = args[1]
    ctx.scope[1 if reverse else -1][vname] = val
    return [val]

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
    async def cat(ctx, args):
        return ["".join(args)]

    @staticmethod
    async def exec(ctx, args):
        # run empty command
        if len(args) < 1:
            ctx.error("exec invoked with no arguments")
            return []

        # find executable
        exec_path = shutil.which(args[0])
        if exec_path is None:
            ctx.error("could not find executable %s" % args[0])
            return []
        args[0] = exec_path

        if ctx.dry_run:
            logger.info("DRY RUN: Running %s", " ".join(args))
            return ["<DRY RUN - COMMAND NOT EXECUTED>"]

        # log redirection & capture
        logger.debug("Invoking %s", shlex.join(args))
        ctx.log_stdout("Invoking %s" % shlex.join(args))

        stdout = ""
        max_len = ctx.config["max_value_len"]

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

        return [stdout]


async def run_stdlib_func(ctx, cmd, args):
    if not hasattr(DslStdlib, cmd):
        return None
    result = await getattr(DslStdlib, cmd)(ctx, args)
    if result is None:
        ctx.error("builtin DSL function {} did not return a result!")
        return [""]
    return result

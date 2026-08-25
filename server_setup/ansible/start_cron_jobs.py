#!/usr/bin/env python3
# NOTE: IMPORTANT: This file is a JINJA template
# NOTE: IMPORTANT: This file SHOULD NOT generate stdout/err output on success as it is a cron job
# NOTE: IMPORTANT: This file is fairly critical and should recover from most errors!
import asyncio
import dataclasses
import datetime
import functools
import inspect
import os
from pathlib import Path
import pwd
import shlex
import subprocess
import sys
import time
import traceback

BEANCRON_VERSION = "1.0.0"

# Relevant available variables:
NEW_USER_NAME = """{{ new_user_name }}"""  # e.g. 'tom_scott'
CRON_SCRIPTS_PATH = """{{ cron_scripts_path }}"""  # e.g. 'Monthly', 'Hourly', etc.

# Configurable variables
SECURE_LOG_PERMS = 0o600
USER_LOG_PERMS = 0o644

# Generated variables
RUN_DATE = time.time_ns() // 10**9

# Run a little sanity check
if "{" in NEW_USER_NAME:
    print("Hey! Beancron is a JINJA template, make sure you template beancron before running.")

HOME_FOLDER = Path(pwd.getpwnam(NEW_USER_NAME).pw_dir)

SECURE_SCRIPTS_PATH = HOME_FOLDER / f"secure/Crons/{CRON_SCRIPTS_PATH}"
USER_SCRIPTS_PATH = HOME_FOLDER / f"Crons/{CRON_SCRIPTS_PATH}"

SECURE_LOG_FOLDER = HOME_FOLDER / "secure/Logs/Cron/"
USER_LOG_FOLDER = HOME_FOLDER / "Logs/Cron/"
CRON_LOG_FILE = SECURE_LOG_FOLDER / f"beancron_run_{str(RUN_DATE)}.log"


def quick_bailout():
    """
    Run some quick checks and fail fast or warn the user if it's not a good idea to
    run beancron.
    """
    for i in [SECURE_LOG_FOLDER, USER_LOG_FOLDER]:
        assert i.is_dir(), str(i) + " does not exist!"

    if os.geteuid() != 0:
        print("Beancron requires running as root as runuser cannot be used without uid=0.")
        # ~/secure should be 0o700, owned by root. Nothing will run anyways in the default setup.

    script_os_stat = Path(__file__).stat()
    if script_os_stat.st_mode & 0o022 != 0 or script_os_stat.st_uid != os.geteuid():
        print("Beancron's script is alterable by users other than the current user!")
        print("Make sure ansible installs this file w/ owner 0 & mode 700")
        print("OR make sure you're running as the right user (did you forget sudo while debugging?)")
        sys.exit(1)


quick_bailout()


# Since umask is set later on, we need to initialise log_file after main().
# Look in log_quiet for initialisation
log_file = None


def log_quiet(*args, **kwargs):
    """
    Log in a file. Same semantics and arguments as print() minus flush= and file=
    arguments.
    """
    global log_file
    if log_file is None:
        log_fd = os.open(
            path=CRON_LOG_FILE,
            flags=(os.O_RDWR | os.O_EXCL | os.O_CREAT),
            mode=SECURE_LOG_PERMS,
        )
        log_file = open(log_fd, "w")

    print("BEANCRON", *args, **kwargs, file=log_file, flush=True)


def log_loud(*args, **kwargs):
    """
    Log in a file and to stderr. Same semantics and arguments as print() minus
    flush= and file= arguments.
    """
    log_quiet("UHOH!", *args, **kwargs)
    print("BEANCRON UHOH!", *args, **kwargs, file=sys.stderr)


def infallible(task_detail_func = None, default_return = None):
    """
    Make sure a function fails gracefully and returns default_return if it throws
    an exception.

    task_detail_func is a function that takes the same arguments as the wrapped
    function and completes the sentence 'Failed while trying to ____' with a helpful
    description of what actually failed.
    """
    def _dummy_detail(*_args, **_kwargs):
        return "do something"

    def handle_exception(e, default, *args, **kwargs):
        trace = "".join(traceback.format_exc())
        log_loud(f"Failed while trying to {task_detail_func(*args, **kwargs)}: {e}")
        for i in trace.splitlines():
            log_loud("EXC", i)
        
        return default

    if task_detail_func is None:
        task_detail_func = _dummy_detail

    # Don't worry, I can't read this either.
    def decorator(function):
        # Handle async functions
        if inspect.iscoroutinefunction(function):
            @functools.wraps(function)
            async def infallible_wrapper(*args, **kwargs):
                try:
                    return await function(*args, **kwargs)
                except Exception as e:
                    return handle_exception(e, default_return, *args, **kwargs)

            return infallible_wrapper

        # Handle sync functions
        else:
            @functools.wraps(function)
            def infallible_wrapper(*args, **kwargs):
                try:
                    return function(*args, **kwargs)
                except Exception as e:
                    return handle_exception(e, default_return, *args, **kwargs)

            return infallible_wrapper
    return decorator


@dataclasses.dataclass
class JobConf:
    script_path: Path
    is_secure: bool

    def get_log_path(self) -> Path:
        parent_dir = SECURE_LOG_FOLDER if self.is_secure else USER_LOG_FOLDER
        filename = (
            f"run_{str(RUN_DATE)}_{CRON_SCRIPTS_PATH}_{self.script_path.name}.log"
        )
        return parent_dir / filename

    @infallible(lambda self: f"run script {self.script_path}")
    async def run(self):
        perms = SECURE_LOG_PERMS if self.is_secure else USER_LOG_PERMS

        # Set up command line arguments
        program_args = [str(self.script_path)]
        if not self.is_secure:
            program_args = ["runuser", "-u", NEW_USER_NAME, "--"] + program_args
        shlex_args = shlex.join(program_args)

        # Set up log file
        log_path = self.get_log_path()
        # This fd is passed directly to asyncio, no file opening needed
        log_fd = os.open(
            path=log_path, flags=(os.O_RDWR | os.O_EXCL | os.O_CREAT), mode=perms
        )

        # Run the command!
        log_quiet(f"Running command {shlex_args}, with logs going to {log_path}")
        start_time = time.time_ns()

        process = await asyncio.create_subprocess_exec(
            *program_args,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            stdout=log_fd,
        )
        returncode = await process.wait()

        os.close(log_fd)

        # Report time elapsed
        time_elapsed = (time.time_ns() - start_time) / 10**9
        log_quiet(f"Command {shlex_args} finished running! Took {time_elapsed}s")

        if returncode != 0:
            log_loud(
                f"Cron task at {self.script_path} failed with code {returncode}. See {log_path} for logs."
            )

@infallible(lambda path, is_secure: f"look for jobs at {path}", [])
def find_jobs(path: Path, is_secure: bool) -> list[asyncio.Task]:
    """
    Find all runnable and safe scripts at `path`, create a JobConf for each, run
    the job, and return the future for the job.
    """
    # TODO: SECURITY: Check for TOCTTOU vulnerabilities that an unprivileged user
    # can exploit? We assume ~/secure is owned by root and has 0o700 perms.
    if not path.is_dir():
        log_loud(f"Cron scripts path {path} is not a valid directory!")
        return []

    if is_secure:
        # Security check: check if path to secure crons is clean
        if path.resolve() != path:
            log_loud(f"Cron scripts path {path} has symlinks! (real path: {path.resolve()})")
            return []
        # Security check: check folder mode
        if path.stat().st_mode & 0o077 != 0:
            log_loud(f"Cron scripts path {path} has bad permissions (expected 0o700, got {oct(path.stat().st_mode & 0o777)})")
            return []

    jobs = []

    for script in path.iterdir():
        if is_secure:
            if script.is_symlink():
                log_loud(f"Secure cron script {script} is a symlink.")
                continue
            if script.stat().st_mode & 0o077 != 0:
                log_loud(f"Secure cron script {script} has bad permissions (expected 0o700, got {oct(script.stat().st_mode & 0o777)})")
                continue

        if not script.is_file():
            log_loud(f"Cron script {script} is not a file.")
            continue
        if script.stat().st_mode & 0o111 == 0:
            log_loud(f"Cron script {script} is not executable.")
            continue

        new_job = JobConf(
            script_path=script,
            is_secure=is_secure,
        )

        log_quiet(
            f"Found new {'secure ' if is_secure else ''}job at {new_job.script_path}, dispatching..."
        )
        # We just save this future and await it later.
        jobs.append(asyncio.create_task(new_job.run()))

    return jobs


async def main():
    # Double make sure that we're umask 0
    os.umask(0)

    start = time.time_ns()

    log_quiet(
        f"Started Beancron v{BEANCRON_VERSION}! Running {CRON_SCRIPTS_PATH} jobs. {datetime.datetime.now().strftime('%c')}"
    )

    jobs = []

    # Find jobs and dispatch them as we find them
    jobs += find_jobs(SECURE_SCRIPTS_PATH, is_secure=True)
    jobs += find_jobs(USER_SCRIPTS_PATH, is_secure=False)

    # Wait for all jobs
    if len(jobs) != 0:
        await asyncio.wait(jobs)

    time_elapsed = (time.time_ns() - start) / 10**9
    log_quiet("Finished running beancron! Took: %ss" % time_elapsed)


if __name__ == "__main__":
    asyncio.run(main())

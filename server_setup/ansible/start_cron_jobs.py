#!/usr/bin/env python3
# NOTE: IMPORTANT: This file is a JINJA template
# NOTE: IMPORTANT: This file SHOULD NOT generate stdout/err output as it is a cron job
# NOTE: IMPORTANT: This file is critical and should recover from errors!
import asyncio
import dataclasses
import datetime
import os
from pathlib import Path
import pwd
import shlex
import subprocess
import sys
import time
import traceback

os.umask(0)

BEANCRON_VERSION = "0.0.1"

# Relevant available variables:
NEW_USER_NAME = """{{ new_user_name }}"""  # e.g. 'tom_scott'
CRON_SCRIPTS_PATH = """{{ cron_scripts_path }}"""  # e.g. 'Monthly', 'Hourly', etc.

# Configurable variables
SECURE_LOG_PERMS = 0o600
USER_LOG_PERMS = 0o644

TIMEOUT_WARNING = 60

# Generated variables
RUN_DATE = time.time_ns() // 10**9

HOME_FOLDER = pwd.getpwnam(NEW_USER_NAME).pw_dir

SECURE_SCRIPTS_PATH = HOME_FOLDER / f"secure/Crons/{CRON_SCRIPTS_PATH}"
USER_SCRIPTS_PATH = HOME_FOLDER / f"Crons/{CRON_SCRIPTS_PATH}"

SECURE_LOG_FOLDER = HOME_FOLDER / "secure/Logs/Cron/"
USER_LOG_FOLDER = HOME_FOLDER / "Logs/Cron/"
CRON_LOG_FILE = HOME_FOLDER / f"secure/Logs/Cron/beancron_run_{str(RUN_DATE)}.log"

# NOTE: features you can cut out if you'd like to keep beancron more minimal:
# 1. Timeouts (This can kinda be helpful with debugging but as always you can just check the log to see what started and didn't finish.)
# 2. Use anacron TwT
# 3. Secure/insecure (or user) distinction (I wanna keep this because it helps being able to write scripts entirely unprivileged)
# 4. Unneccesary security / file checks that will error out eventually (this is very suckless esque, i like it, but it does make your script kinda gross)
# 5. Security checks

# Since umask is set later on, we need to initialise log_file after main().
# log_file is initialised in log_quiet()
log_path = CRON_LOG_FILE
log_fd = os.open(
    path=log_path,
    flags=(os.O_RDWR | os.O_EXCL | os.O_CREAT),
    mode=SECURE_LOG_PERMS,
)
log_file = open(log_fd, "w")


def log_quiet(*args, **kwargs):
    global log_file
    print("BEANCRON", *args, **kwargs, file=log_file, flush=True)


def log_loud(*args, **kwargs):
    log_quiet("UHOH!", *args, **kwargs)
    print("BEANCRON UHOH!", *args, **kwargs, file=sys.stderr)


@dataclasses.dataclass
class JobConf:
    script_path: Path
    is_secure: bool

    def get_log_path(self) -> str:
        parent_dir = SECURE_LOG_FOLDER if self.is_secure else USER_LOG_FOLDER
        filename = (
            f"run_{str(RUN_DATE)}_{CRON_SCRIPTS_PATH}_{self.script_path.name}.log"
        )
        return parent_dir / filename

    async def _run(self):
        perms = SECURE_LOG_PERMS if self.is_secure else USER_LOG_PERMS

        # Set up log file
        log_path = self.get_log_path()
        # This fd is passed directly to asyncio, no file opening needed
        log_fd = os.open(
            path=log_path, flags=(os.O_RDWR | os.O_EXCL | os.O_CREAT), mode=perms
        )

        # Set up command line arguments
        program_args = [str(self.script_path)]
        if not self.is_secure:
            program_args = ["runuser", "-u", NEW_USER_NAME, "--"] + program_args
        shlex_args = shlex.join(program_args)

        # Run the command!
        log_quiet(f"Running command {shlex_args}, with logs going to {log_path}")
        start_time = time.time_ns()
        process = await asyncio.create_subprocess_exec(
            *program_args,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            stdout=log_fd,  # I hope asyncio closes this fd, if not idrc
        )
        process_future = process.wait()
        try:
            returncode = await asyncio.wait_for(
                asyncio.shield(process_future), TIMEOUT_WARNING
            )
        except TimeoutError:
            log_loud(f"Command {shlex_args} is taking way too long!")
            returncode = await process_future

        assert returncode is not None, (
            "BUG: Whoops! we didn't wait for the process to finish!"
        )

        time_elapsed = (time.time_ns() - start_time) / 10**9

        log_quiet(f"Command {shlex_args} finished running! Took {time_elapsed}s")

        if returncode != 0:
            log_loud(
                f"Cron task at {self.script_path} failed with code {returncode}. See {log_path} for logs."
            )

    async def run(self):
        try:
            return await self._run()
        except Exception as e:
            trace = "".join(traceback.format_exc())
            log_loud(f"Failed while trying to run script {self.script_path}: {e}")
            for i in trace.splitlines():
                log_loud("EXC", i)


def find_jobs(path: Path, is_secure: bool) -> list[asyncio.Task]:
    # TODO: SECURITY: Check for TOCTTOU vulnerabilities that an unprivileged user
    # can exploit? We assume ~/secure is owned by root and has 0o700 perms.
    if not path.is_dir():
        log_loud(f"Cron scripts path {path} is not a valid directory!")
        return []

    if is_secure:
        # Security check: check if path to secure crons is clean
        if path.resolve() != path:
            log_loud(
                f"Cron scripts path {path} has symlinks! (real path: {path.resolve()})"
            )
            return []
        # Security check: check folder mode
        if path.stat().st_mode & 0o077 != 0:
            log_loud(
                f"Cron scripts path {path} has bad permissions (expected 0o700, got {oct(path.stat().st_mode)})"
            )
            return []

    jobs = []

    for script in path.iterdir():
        if is_secure:
            if script.is_symlink():
                log_loud(f"Secure cron script {script} is a symlink.")
                continue
            if script.stat().st_mode & 0o077 != 0:
                log_loud(
                    f"Secure cron script {script} has bad permissions (expected 0o700, got {oct(script.stat().st_mode)})"
                )
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

    if os.geteuid() != 0:
        log_loud(
            "Beancron requires running as root as runuser cannot be used without uid=0."
        )
        log_loud("Continuing anyways")

    if '{' in NEW_USER_NAME:
        log_loud("Beancron is a JINJA template, make sure you template beancron before running.")
        log_loud("Continuing anyways")

    script_os_stat = Path(__file__).stat
    if script_os_stat.st_mode & 0o022 != 0 or script_os_stat.st_uid != os.geteuid():
        log_loud("Beancron's script is alterable by users other than the current user!")
        log_loud(f"Make sure you run chown 0 {__file__} and chmod 700 {__file__}")
        return

    log_quiet(
        f"Started Beancron v{BEANCRON_VERSION}! Running {CRON_SCRIPTS_PATH} jobs. {datetime.datetime.now().strftime('%c')}"
    )

    jobs = []

    # Run secure jobs
    jobs += find_jobs(SECURE_SCRIPTS_PATH, is_secure=True)
    jobs += find_jobs(USER_SCRIPTS_PATH, is_secure=False)

    # Run user jobs
    if len(jobs) != 0:
        await asyncio.wait(jobs)


if __name__ == "__main__":
    asyncio.run(main())

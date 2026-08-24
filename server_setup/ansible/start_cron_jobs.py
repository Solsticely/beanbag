#!/usr/bin/env python3
# NOTE: IMPORTANT: This file is a JINJA template
# NOTE: IMPORTANT: This file SHOULD NOT generate stdout/err output as it is a cron job
# NOTE: IMPORTANT: This file is critical and should recover from errors!
import asyncio
import dataclasses
import datetime
import gzip  # Your python package needs to be configured with gzip to run beancron
import os
from pathlib import Path
import pwd
import shlex
import shutil
import subprocess
import sys
import time
import traceback

BEANCRON_VERSION = "0.0.1"
RUN_DATE = time.time_ns() // 10**9

# Relevant available variables:
NEW_USER_NAME = """{{ new_user_name }}"""  # e.g. 'tom_scott'
CRON_SCRIPTS_PATH = """{{ cron_scripts_path }}"""  # e.g. 'Monthly', 'Hourly', etc.

# Generated variables
HOME_FOLDER = pwd.getpwnam(NEW_USER_NAME).pw_dir

# Script paths are /home/{{ new_user_name }}/{secure/,}Crons/{{ cron_scripts_path }}
SECURE_SCRIPTS_PATH = HOME_FOLDER / f"secure/Crons/{CRON_SCRIPTS_PATH}"
USER_SCRIPTS_PATH = HOME_FOLDER / f"Crons/{CRON_SCRIPTS_PATH}"

# NOTE: features you can cut out if you'd like to keep beancron more minimal:
# 1. GZIP logs
# 2. Timeouts
# 3. Use anacron TwT

# TODO: assert that we're running as root or other privileged user
# TODO: assert that we have access to runuser
# TODO: assert that current script is not editable by other users (has umask 0o077 at the very least and 0o277 ideally)

# TODO: all logs should be owned by root and stored at /home/{{ new_user_name }}/{secure/,}Logs/Cron/run_%date%_{{ cron_scripts_path }}_%script_name%.txt.gz
SECURE_LOG_FOLDER = HOME_FOLDER / "secure/Logs/Cron/"
USER_LOG_FOLDER = HOME_FOLDER / "Logs/Cron/"
CRON_LOG_FILE = HOME_FOLDER / f"secure/Logs/Cron/beancron_run_{str(RUN_DATE)}.txt"

# TODO: run all scripts as root                from /home/{{ new_user_name }}/secure/Crons/{{ cron_scripts_path }} EXCEPT this script
# TODO: run all scripts as {{ new_user_name }} from /home/{{ new_user_name }}/Crons/{{ cron_scripts_path }}
# TODO: run all commands asynchronously
# TODO: non-secure run logs should have chmod 644, secure run logs should have chmod 600
SECURE_LOG_PERMS = 0o600
USER_LOG_PERMS = 0o644

COMPRESSED_LOG_EXTENSION = ".gz"
TIMEOUT_WARNING = 60

# Since umask is set later on, we need to initialise log_file after main().
# log_file is initialised in log_quiet()
log_file = None


def log_quiet(*args, **kwargs):
    global log_file
    if log_file is None:
        # We need umask set up, that's why we're initialising log_file here instead.
        log_path = CRON_LOG_FILE
        log_fd = os.open(
            path=log_path,
            flags=(os.O_RDWR | os.O_EXCL | os.O_CREAT),
            mode=SECURE_LOG_PERMS,
        )
        log_file = open(log_fd, "w")

    print("BEANCRON", *args, **kwargs, file=log_file)


def log_loud(*args, **kwargs):
    log_quiet("UHOH!", *args, **kwargs)
    print("BEANCRON UHOH!", *args, **kwargs, file=sys.stderr)


# Things we need to log:
# 1. which jobs are found
# 2. each job's status as they are started and they finish
# 3. warnings if jobs take too long
# 4. time each job took to finish


@dataclasses.dataclass
class JobConf:
    script_path: Path
    is_secure: bool

    def get_log_path(self, is_compressed: bool = False) -> str:
        extension = ".log" + COMPRESSED_LOG_EXTENSION if is_compressed else ".log"
        parent_dir = SECURE_LOG_FOLDER if self.is_secure else USER_LOG_FOLDER
        filename = f"run_{str(RUN_DATE)}_{CRON_SCRIPTS_PATH}_{self.script_path.name}{extension}"
        return parent_dir / filename

    async def _run(self):
        # Steps:
        # 1. create log file, set owner & perms
        # 2. run job AS APPROPRIATE USER and pipe into log file (use runuser)
        # 3. when job is done, create new compressed log file with appropriate owner & perms
        # 4. remove old log file
        perms = SECURE_LOG_PERMS if self.is_secure else USER_LOG_PERMS

        # Set up uncompressed log file
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
        log_quiet(
            f"Running command {shlex_args}, with logs going to {log_path}"
        )
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

        log_quiet(
            f"Command {shlex_args} finished running! Took {time_elapsed}s"
        )

        # Compress the log!
        if returncode != 0:
            log_loud(
                f"Cron task at {self.script_path} failed with code {returncode}. See {log_path} for logs."
            )

        # create compressed log
        comp_log_path = self.get_log_path(is_compressed=True)
        comp_log_fd = os.open(
            path=comp_log_path, flags=(os.O_RDWR | os.O_EXCL | os.O_CREAT), mode=perms
        )
        log_quiet(
            f"Compressing logs for cronjob at {self.script_path}: {log_path} -> {comp_log_path}"
        )
        with open(comp_log_fd, "wb") as comp_log_file:
            with gzip.open(comp_log_file, "wb") as newfile:
                with open(log_path, "rb") as oldfile:
                    shutil.copyfileobj(oldfile, newfile)
        log_quiet(f"Finished compressing logs for cronjob at {self.script_path}")

        # only remove old log if run was successful
        if returncode == 0:
            log_quiet(
                f"Removing uncompressed logs for {self.script_path} as no error was encountered."
            )
            log_path.unlink()

    async def run(self):
        try:
            return await self._run()
        except Exception as e:
            trace = "".join(traceback.format_exception(e))
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
                log_loud(f"Secure cron script {path} is a symlink.")
                continue
            if script.stat().st_mode & 0o077 != 0:
                log_loud(
                    f"Secure cron script {path} has bad permissions (expected 0o700, got {oct(script.stat().st_mode)})"
                )
                continue

        if not script.is_file():
            log_loud(f"Cron script {path} is not a file.")
            continue
        if script.stat().st_mode & 0o111 == 0:
            log_loud(f"Cron script {path} is not executable.")
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
    # with help from:
    # - https://stackoverflow.com/questions/36745577
    os.umask(0)

    if os.geteuid() != 0:
        log_loud("Beancron requires running as root as runuser cannot be used without uid=0.")
        log_loud("Continuing anyways; ")

    log_quiet(
        f"Started Beancron v{BEANCRON_VERSION}! Running {CRON_SCRIPTS_PATH} jobs. {datetime.datetime.now().strftime('%c')}"
    )

    jobs = []

    # Run secure jobs
    # def find_jobs(user: int | str, path: Path, is_secure: bool) -> list
    jobs += find_jobs(SECURE_SCRIPTS_PATH, True)
    jobs += find_jobs(USER_SCRIPTS_PATH, False)

    # Run user jobs
    if len(jobs) != 0:
        await asyncio.wait(jobs)


if __name__ == "__main__":
    asyncio.run(main())

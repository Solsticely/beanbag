#!/usr/bin/env python3
import asyncio
import time
import logging
import dsl as bb_dsl
import config as bb_conf
import security

logger = logging.getLogger("beanbag")

ERRORS = {
    "no_appdir": "Beanbag can not find app directory! Use --home_dir=PATH to set a custom directory!"
}


def main():
    logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s %(levelname)-8s %(name)-8s] %(message)s")

    # parse arguments
    # if len(sys.argv) <= 1:
    #     logging.error("Too few arguments! Usage: beanbag.py <COMMAND> [<ARGS>*]")
    #     logging.error("Valid <command>s are: %s", "provision run update package".split())
    #     logging.error("To get all valid arguments for a given command, run beanbag.py <command> --help")
    #     exit(1)

    config = bb_conf.get_args_and_config()

    # run
    match config.command:
        case "provision":
            asyncio.run(provision(config))

        case "run":
            asyncio.run(run(config))

        case "update":
            update(config)

        case "package":
            extract_deployment(config)


async def provision(config, warn_existing_datafiles=False):
    # TODO: grab mutex
    if is_provisioned(config):
        logger.warning("App directory already exists! Re-provisioning may delete important existing files!")
        if not config.args.force_provision:
            logger.warning("If you want to try to provision anyhow, use `--force-provision`.")
            logger.warning("If you'd like to update, use ‘beanbag.py update’ instead.")
            exit(1)
        else:
            logger.warning("Provisioning over the previous app directory")

    provis_path = config.provis_path
    services = config.selected_services
    logger.info("Provisioning to %s...", provis_path)

    # set up directory structure
    if not provis_path.parent.is_dir():
        logger.warning("App directory's parent folder %s doesn't exist, creating...", provis_path.parent)
    provis_path.mkdir(parents=True, exist_ok=True)

    dirs_to_be_made = 'workdirs datafiles logs mutexes'.split()
    for p in dirs_to_be_made:
        (provis_path/p).resolve().mkdir(parents=False, exist_ok=True)

    # make a directory for each service id in folders workdirs and datafiles
    for p in 'workdirs datafiles'.split():
        for s in services:
            (provis_path/p/s).resolve().mkdir(parents=False, exist_ok=True)

    # touch all logfiles for all services
    for s in services:
        (provis_path/'logs'/(s+".log")).touch()

    # copy over all setupfiles from beanbag/services/*.setupfiles/
    # in case of a reprovision, we will warn the user instead and then override
    # any existing files.
    # TODO: make this a hard symlink that is read-only.
    for s in services:
        for filepath, fileread in config.services[s].setupfiles.items():
            with fileread() as instream:
                with open((provis_path/'workdirs'/s/filepath).resolve(), "wb") as outstream:
                    outstream.write(instream.read())  # TODO: streaming copy

    for id in services:
        service = config.services[id]
        await bb_dsl.run_commands(config, id, service.provision)

    # refresh symlinks
    refresh_symlinks(config)

    logger.info("Succesfully provisioned to %s!", provis_path)
    pass


def is_provisioned(config):
    # intentionally not using is_dir to raise natural error for nondirectory
    # entries
    for id in config.selected_services:
        if not security.workdir(config, id).exists():
            return False
    return True


def refresh_symlinks(config):
    pass  # TODO: write refresh symlinks


async def service_worker_loop(config, id: str):
    service = config.services[id]
    retry = service.run.on_exit == "retry"

    while True:
        await bb_dsl.run_commands(config, id, service.run)
        logger.warning("Service %s stopped running!", service.name)

        if retry:
            logger.info("Killing service %s", service.name)
            await bb_dsl.run_commands(config, id, service.kill, extra_envs=[service.run.env])

            await asyncio.sleep(9)
            logger.info("Starting service %s", service.name)
        else:
            break


async def run(config):
    if not is_provisioned(config):
        logger.critical(ERRORS["no_appdir"] + "Did you forget to run ‘beanbag.py provision’ first?")
        security.halt()

    # TODO: delete all mutexes in mutexes/ folder if they aren't locked already
    # TODO: start job that watches for globfile creation and updates symlinks
    # Populate jobs
    jobs = [service_worker_loop(config, id) for id in config.selected_services]
    async def init_done(): logger.info("Started all services!")
    jobs.append(init_done())

    # Start all services in parallel
    await asyncio.gather(*jobs)

    # All jobs started, wait for all services to exit
    logger.warning("All runners stopped executing! Looping forever...")
    while True:
        time.sleep(1)


def update(config):
    # TODO: grab mutex
    if not is_provisioned(config):
        logger.critical(ERRORS["no_appdir"])
        security.halt()
    pass  # TODO: implement updating


def extract_deployment(config):
    if not is_provisioned():
        logger.critical(ERRORS["no_appdir"])
        security.halt()
    # TODO: extract deployment
    pass


if __name__ == "__main__":
    main()

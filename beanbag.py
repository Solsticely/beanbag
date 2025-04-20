#!/usr/bin/env python3
# import sys
import tomllib
import asyncio
# import os
from pathlib import Path
# from zipfile import ZipFile
import argparse
import time
import logging
import dsl as bb_dsl

logger = logging.getLogger(__name__)

ERRORS = {
    "no_appdir": "Beanbag can not find app directory! Use --home_dir=PATH to set a custom directory!"
}


def main():
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s\t%(name)s\t%(message)s")

    # parse arguments
    # if len(sys.argv) <= 1:
    #     logging.error("Too few arguments! Usage: beanbag.py <COMMAND> [<ARGS>*]")
    #     logging.error("Valid <command>s are: %s", "provision run update package".split())
    #     logging.error("To get all valid arguments for a given command, run beanbag.py <command> --help")
    #     exit(1)

    config = get_args_and_config()

    # run
    match config["command"]:
        case "provision":
            asyncio.run(provision(config))

        case "run":
            run(config)

        case "update":
            update(config)

        case "package":
            extract_deployment(config)


def get_config(args):
    # TODO: parse actual config
    # TODO: dynamic getattr
    config = {
        "command": args.command,
        "is_loud": args.command in {"provision", "update"},
        "halt_on_error": args.command in {"provision", "update", "package"},
        "provis_path": args.app_dir or (args.beanbag.resolve().parent / "beans"),
        "config_path": args.beanbag.resolve(),
        "services": {},  # Is filled later on
        "max_value_len": 1024*1024*20,  # 20MiO
        "lib": {},  # Is filled later on
        "args": args,
        "dry_run": args.dry_run
    }
    # TODO: validate that service ids are valid directory names
    # TODO: validate all paths are relative and don't escape
    # TODO: generalise loading, implement loading from zip
    services = config["config_path"].glob("services/*.toml")
    for srv_path in services:
        srv_toml = tomllib.load(open(srv_path, "rb"))

        x = {item[:2]: srv_toml.get(item) or {} for item in "service storage logging run update kill provision".split()}

        srv_id = x["se"].get("id") or srv_path.name

        service = {
            "setupfiles": {},  # is filled later
            # [service]
            "name": x["se"].get("name") or srv_id,

            # [storage]
            "datafile_globs": x["st"].get("datafiles") or [],
            "datafile_blacklist_globs": x["st"].get("blacklist"),

            # [logging]
            "log_policy": x["lo"].get("policy") or {},  # TODO: design log policies
            "log_artifact_glob": x["lo"].get("artifacts") or [],
            "log_artifact_blacklist_glob": x["lo"].get("blacklist") or [],

            # [provision]
            "provision": config_parse_dsl(x["pr"]),

            # [kill]
            "kill": config_parse_dsl(x["ki"]),

            # [run]
            "run": {
                "on_exit": x["ru"].get("on_exit") or "rerun",
                **config_parse_dsl(srv_toml.get("run"))
            }
        }

        # [update]
        update_type = x["up"].get("type") or "reprovision"
        kill_before = x["up"].get("kill_before")
        kill_before = True if kill_before is None else kill_before

        service["update"] = {
            # TODO: make update get parsed as an actual command.
            # INFO: If type is reprovision, have pre-execute, provision, and post-execute
            # all concatenated into a command inside update
            "update": None,
            "get_version": bb_dsl.parse_dsl(x["up"].get("get_version") or []),
            "update_type": update_type,
            "pre_execute": bb_dsl.parse_dsl(x["up"].get("pre_execute") or []),
            "post_execute": bb_dsl.parse_dsl(x["up"].get("post_execute") or []),
            "kill_before": kill_before
        }

        # grab setupfiles
        setupfiles = config["config_path"] / "services" / (srv_path.name + ".setupfiles")

        # don't check if its a directory so we raise an OS error if it isnt
        if setupfiles.exists():
            for (root, dirs, files) in setupfiles.walk(follow_symlinks=True):
                # TODO: empty directories
                for file in files:
                    filepath = root/file
                    filepath_capture = filepath.resolve()
                    service["setupfiles"][filepath] = lambda: open(filepath_capture, "rb")

        config["services"][srv_id] = service

    libraries = config["config_path"].glob("library/*.toml")
    for library in libraries:
        lib_toml = tomllib.load(open(library, "rb"))
        cmds = lib_toml.get("command")
        if cmds is None:
            continue
        for ident, cmd in cmds.items():
            if ident in config["lib"]:
                ctx = bb_dsl.Ctx(src=library, halt_on_error=True)
                ctx.error("Library function %s registered twice" % ident, True)
                # <unreachable>
            config["lib"][ident] = {
                "body": bb_dsl.parse_dsl(cmd["body"]),
                "usage": cmd.get("usage") or "<USAGE NOT PROVIDED>",
            }

    return config


def get_args_and_config():
    # TODO: make cmd detection dynamic, with groups maybe?
    # INFO: subparsers is a feature specifically made for this purpose, see:
    # https://docs.python.org/3/howto/logging-cookbook.html#a-cli-application-starter-template
    # TODO: make loglevel dynamic, see:
    # https://docs.python.org/3/howto/logging-cookbook.html#a-cli-application-starter-template
    # TODO: add minecraft-style logging where logs are written to a file aswell
    # as being returned.
    parser = argparse.ArgumentParser()
    # parser.add_argument("command",
    #                     choices="provision run update package".split())
    parser.add_argument("--beanbag", "-i", type=Path,
                        default=Path.cwd()/"beanbag", help="""The location
                        of a playbook config or a zip package""")
    parser.add_argument("--app-dir", "-o", type=Path, default=None, help="""The
                        location of where the deployment is stored. If not
                        provided, defaults to a sibling directory to the parent
                        directory of the beanbag named ‘beans’""")
    parser.add_argument("--dry-run", action="store_true", help="""Print the
                        commands run instead of running them""")

    cmds = parser.add_subparsers(title="Command", dest="command", help="command help", required=True)

    # provisioning
    # TODO: add ability to provision or run only a single service
    # cmd_prov = cmds.add_parser("provision", aliases="p prov s setup".split())
    cmd_prov = cmds.add_parser("provision")
    cmd_prov.add_argument("--force-provision", "-f", action="store_true",
                          help="""Force a provision, even if the app
                          directory already exists""")

    # update subcommand
    # cmd_update = cmds.add_parser("update", aliases="u upgrade upgr".split())
    cmd_update = cmds.add_parser("update")
    cmd_update.add_argument("service")  # TODO: add specific-service updating

    # run subcommand
    # TODO: add ability to provision, run or package a subset of all services
    # cmd_run = cmds.add_parser("run", aliases="r execute x".split())
    cmd_run = cmds.add_parser("run")
    (cmd_run,)

    # package subcommand
    # cmd_pack = cmds.add_parser("package", aliases="pack zip z".split())
    cmd_pack = cmds.add_parser("package")
    (cmd_pack,)

    # logger.debug(parser.parse_args())
    return get_config(parser.parse_args())


def is_provisioned(config):
    return True  # FIXME: implement proper provision detection


def config_parse_dsl(config_section):
    """
    Grabs a config section with subcommands "envs" and "commands" and returns
    a table with both fields normalised.

    Additionally, converts dictionary notation for the DSL into lisp-like
    notation.
    """
    config_section = config_section or {}
    command = config_section.get("commands")
    if command is None:
        return {"cmd": [], "env": {}}  # return NOP if no command provided

    envs = config_section.get("envs") or {}

    return {
        "cmd": bb_dsl.parse_dsl(command),
        "env": envs
    }


async def provision(config, warn_existing_datafiles=False):
    # TODO: grab mutex
    if is_provisioned(config):
        logger.warning("App directory already exists! Re-provisioning may delete important existing files!")
        if not config["args"].force_provision:
            logger.warning("If you want to try to provision anyhow, use `--force-provision`.")
            logger.warning("If you'd like to update, use ‘beanbag.py update’ instead.")
            exit(1)
        else:
            logger.warning("Provisioning over the previous app directory")

    provis_path = config["provis_path"]
    services = config["services"]
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
        for filepath, fileread in services[s]["setupfiles"].items():
            with fileread() as instream:
                with open((provis_path/'workdirs'/s/filepath).resolve(), "wb") as outstream:
                    outstream.write(instream.read())  # TODO: streaming copy

    for s in services:
        await bb_dsl.run_commands(config, services[s]["provision"]["cmd"], s, (provis_path/'workdirs'/s).resolve())

    # refresh symlinks
    refresh_symlinks(config)

    logger.info("Succesfully provisioned to %s!", provis_path)
    pass


def refresh_symlinks(config):
    pass  # TODO: write refresh symlinks


def run(config):
    if not is_provisioned(config):
        logger.error(ERRORS["no_appdir"] + "Did you forget to run ‘beanbag.py provision’ first?")
        exit(1)

    # TODO: delete all mutexes in mutexes/ folder if they aren't locked already
    # TODO: start job that watches for globfile creation and updates symlinks
    pass  # TODO: implement running

    logger.warning("All runners stopped executing! Looping forever...")
    while True:
        time.sleep(1)


def update(config):
    # TODO: grab mutex
    if not is_provisioned(config):
        logger.error(ERRORS["no_appdir"])
        exit(1)
    pass  # TODO: implement updating


def extract_deployment(config):
    if not is_provisioned():
        logger.error(ERRORS["no_appdir"])
        exit(1)
    # TODO: extract deployment
    pass


if __name__ == "__main__":
    main()

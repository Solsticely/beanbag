import tomllib
import dsl as bb_dsl
import argparse
from pathlib import Path
from easydict import EasyDict, objectify
import security

import logging as i_am_intentionally_using_logging_instead_of_logger
logger = i_am_intentionally_using_logging_instead_of_logger.getLogger(__name__)


def get_config(args) -> EasyDict:
    # TODO: dynamic getattr
    config = {
        "command": args.command,
        "is_loud": args.command in {"provision", "update"} or args.loud,
        "halt_on_error": args.command in {"provision", "update", "package"} and not args.dry_run,
        "provis_path": args.app_dir or (args.beanbag.resolve().parent / "beans"),
        "config_path": args.beanbag.resolve(),
        "services": {},  # Is filled later on
        "max_value_len": 1024*1024*20,  # 20MiO
        "lib": {},  # Is filled later on
        "args": args,
        "dry_run": args.dry_run,
        "selected_services": set(),  # Is filled later on
    }

    # TODO: validate all paths are relative and don't escape
    # TODO: generalise loading, implement loading from zip
    services = config["config_path"].glob("services/*.toml")
    for srv_path in services:
        srv_toml = tomllib.load(open(srv_path, "rb"))

        # shorten index path: instead of `srv_toml["service"]["id"]` do
        # `x.se.id`. Each subkey is shortened to its first 2 characters. To get
        # `srv_toml["provision"]` we can do `x.pr`.
        x = {item[:2]: srv_toml.get(item) or {} for item in "service storage logging run update kill provision".split()}
        x = objectify(x)

        srv_id = x.se.g("id", srv_path.name)

        service = {
            "path": srv_path,
            "setupfiles": {},  # is filled later
            # [service]
            "name": x.se.g("name", srv_id),
            "id": srv_id,
            "env": x.se.g("envs", {}),

            # [storage]
            "datafile_globs": x.st.g("datafiles", []),
            "datafile_blacklist_globs": x.st.get("blacklist"),

            # [logging]
            "log_policy": x.lo.g("policy", {}),  # TODO: design log policies
            "log_artifact_glob": x.lo.g("artifacts", []),
            "log_artifact_blacklist_glob": x.lo.g("blacklist", []),

            # [provision]
            "provision": config_parse_dsl(x.pr),

            # [kill]
            "kill": config_parse_dsl(x.ki),

            # [run]
            "run": {
                "on_exit": x.ru.g("on_exit", "retry"),
                **config_parse_dsl(x.ru)
            }
        }

        # [update]
        update_type = x.up.g("type", "reprovision")
        kill_before = x.up.get("kill_before")
        kill_before = True if kill_before is None else kill_before

        service["update"] = {
            # TODO: make update get parsed as an actual command.
            # INFO: If type is reprovision, have pre-execute, provision, and post-execute
            # all concatenated into a command inside update
            "update": None,
            "get_version": bb_dsl.parse_dsl(x.up.g("get_version", [])),
            "update_type": update_type,
            "pre_execute": bb_dsl.parse_dsl(x.up.g("pre_execute", [])),
            "post_execute": bb_dsl.parse_dsl(x.up.g("post_execute", [])),
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

    config["selected_services"] = args.service or config["services"].keys()
    extra = config["selected_services"] - config["services"].keys()
    extra = set(extra)
    if len(extra) > 0:
        logger.critical("Selected services don't exist: %s", ", ".join(extra))
        security.halt()

    # TODO: validate that service ids are valid directory names

    libraries = config["config_path"].glob("library/*.toml")
    for library in libraries:
        lib_toml = tomllib.load(open(library, "rb"))
        cmds = lib_toml.get("command")
        if cmds is None:
            continue
        for ident, cmd in cmds.items():
            cmd = objectify(cmd)
            if ident in config["lib"]:
                ctx = bb_dsl.Ctx(src=library, halt_on_error=True)
                ctx.error("Library function %s registered twice" % ident, True)
                # <unreachable>
            config["lib"][ident] = {
                "body": bb_dsl.parse_dsl(cmd.body),
                "usage": cmd.g("usage", "<USAGE NOT PROVIDED>"),
            }

    return objectify(config)


def get_args_and_config():
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
    parser.add_argument("--loud", "-v", action="store_true", help="""Output
                        services' stdout and stderr to the TTY and to log
                        records, instead of only outputting to the log records.
                        """)
    cmds = parser.add_subparsers(title="Command", dest="command", help="command help", required=True)

    # provisioning
    cmd_prov = cmds.add_parser("provision", aliases="p prov s setup".split())
    cmd_prov.add_argument("--force-provision", "-f", action="store_true",
                          help="""Force a provision, even if the app
                          directory already exists""")

    # update subcommand
    cmd_update = cmds.add_parser("update", aliases="u upgrade upgr".split())

    # run subcommand
    cmd_run = cmds.add_parser("run", aliases="r execute x".split())

    # package subcommand
    cmd_pack = cmds.add_parser("package", aliases="pack zip z".split())

    for i in [cmd_update, cmd_prov, cmd_run, cmd_pack]:
        i.add_argument("service", nargs="*", default=None,
                       help="""The services to run the operation on. Specifying
                       no services defaults to all services""")

    # logger.debug(parser.parse_args())
    return get_config(parser.parse_args())


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



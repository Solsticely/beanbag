from pathlib import Path
from easydict import EasyDict
import sys

import logging as i_am_intentionally_using_logging_instead_of_logger
logger = i_am_intentionally_using_logging_instead_of_logger.getLogger(__name__)


# TODO: use this everywhere
def authorise_path(cwd: Path, unsanitised_path: Path, *, soft: bool = False) -> Path | None:
    path = Path.joinpath(cwd, unsanitised_path).resolve()
    if not path.is_relative_to(cwd):
        # TODO: add tmp and cache checks!
        if soft:
            return None
        err = "Path traversal: Tried to authorise path %s outside of all authorised directories"
        logger.error(err, path)
        raise ValueError(err % path)

    # logger.debug("Authorised path %s as %s", unsanitised_path, path)
    return path


def authorise_workdir_path(ctx, unsanitised_path: Path, *, soft: bool = False) -> Path | None:
    try:
        return authorise_path(ctx.cwd, unsanitised_path, soft=soft)
    except ValueError as error:
        ctx.error(str(error), True)


def workdir(config: EasyDict, service: str) -> Path:
    return (config.provis_path/"workdirs"/service).resolve()


def halt(code: int = 1):
    sys.exit(code)

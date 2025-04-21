import security
import time
import os


def truncate(text: str, length: int = 85) -> str:
    return text[:length] + (" [···]" if len(text) > length else "")


def shrink_lines(text: str) -> str:
    return text.replace("\n", '\u23ce')


def clean(text: str, trunc_length: int = 85) -> str:
    return shrink_lines(truncate(text, trunc_length))


def make_log(config, service: str):
    wd = security.workdir(config, service, "logs")
    name = "%s %s %s.log" % (service, config.args.command.upper(), time.strftime("%Y-%m-%d %H:%M:%S"))
    logpath = (wd / name).resolve()
    logfile = open(logpath, "w")
    linkpath = (wd.parent/(service+".log"))
    try:
        os.remove(linkpath)
    except FileNotFoundError:
        pass
    os.symlink(logpath, linkpath)

    return logfile

# Work directory folder structure

A provision results in a work directory, usually named `beans`. The general
structure of the folder is as follows:

```tree
beans/
├ beanbag.lock <mutex for all write operations>
├ last_provision.json <information on the last provisioning>
├ workdirs/ <work directories for all services. logs and datafiles are stored here>
│ ├ service_1/
│ │ └ <working directory of service 1>
│ ├ service_2/
│ │ └ <working directory of service 2>
│ ┆
├ datafiles/ <persistent data and userdata. `beanbag backup` reads from here!>
│ ├ service_1/
│ │ └ <all of service 1’s data files>
│ ├ service_2/
│ │ └ <all of service 2’s data files>
│ ┆
├ logs/ <STDOUT+ERR logs, and symlinks to extra log artifacts in workdirs/>
│ ├ service_1.newest.log <symlink to newest log>
│ ├ service_1.23_12_2025_09_55_16.log
│ ├ service_1.logs/
│ │ └ <symlinks to additional log artifacts in workdirs/>
│ ├ service_2.newest.log <symlink to newest log>
│ ├ service_2.23_12_2025_09_55_16.log
│ ┆
└ mutexes/ <empty files used as mutexes to prevent double-launching services>
  ├ service_1.lock
  ├ service_2.lock
  ┆
```

All folders are documented as follows

## `beanbag.lock` and `mutexes/`

TODO: implement locks as spec

Beanbag uses locks to prevent simple user errors; for
example, when setting up beanbag as a systemd service and forgetting to turn the
services off during an update, or running a service separately and then running
all services at once.

### Global lock (`beanbag.lock`)

The file `beanbag.lock` acts as a global lock to prevent access to any services
during first provision, or packing. The process of acquiring the global lock is
as follows:

1. The file `beanbag.lock` is first locked.
2. Recipe book is read.
3. All, or only the relevant services make and lock their mutex files in `mutexes/`.

*If at any point in this process a lock fails (held by another profile, timeout,
etc.), all previously locked files are to be released and the process either
halts, or repeats. If a lock file doesn't exist, it is created, then locked.*

Processes that require `beanbag.lock` are:

- Modifying `last-provision.json`.
- Provisioning any service, including first provisions, reprovisions and
any services newly registered since last provision.
- Packing the server.
- Clearing unheld `mutexes/`.
- Refreshing symlinks in `datafiles/`
- Refreshing symlinks in `logs/*/`
- Holding mutexes, or parsing the recipe book (global lock is dropped immediately
after the operation is done. The process of holding a service lock uses a
modified procedure, see [Service lock](#service-lock-mutexeslock).

### Service lock (`mutexes/*.lock`)

The service locks act as simple double-running prevention locks, and
additoinally ensure services aren't running during an update.

The process of acquiring a service lock is as follows:

1. The file `beanbag.lock` is first locked.
2. If required, all relevant service data is read from recipe book.
3. If required, all or only the relevant `mutexes/*.lock` files are locked.
4. The global lock, `beanbag.lock` is *dropped*.

*If at any point in this process a lock fails (held by another profile, timeout,
etc.), all previously locked files are to be released and the process either
halts, or repeats. If a lock file doesn't exist, it is created, then locked.*

Processes that require service locks are:

- Running a service.
- Updating log files for a service.
- Updating a service.
- Packing an individual service.

## `last_provision.json`

Last provision holds information about the current provisioning status. Namely:

1. Which services are provisioned? (to detect unprovisioned services during a
reprovision)
2. When each service was provisioned and updated last.
3. List of all persistent data files that are symlinked in
[`datafiles/`](#datafiles) for each service.
4. List of all log files that are symlinked in [`datafiles/`](#datafiles) for
each service.

Modification of this file requires acquiring the [global lock](service-lock-mutexeslock).

## `workdirs/`

This folder is the PWD of each running service.

This folder isn't guaranteed to be persistent, and all persistent data should be
marked as explicitly persistent in the recipes for the service.

## `datafiles/`

This folder contains symlinks to all persistent files for each service.

Every now and then, this folder is cleared, a glob search is done in each
service's workdir, and every matching file is symlinked to from here. The global
lock needs to be held during this operation.

These globs are defined in each service's recipe.

## `logs/`

This folder contains log files (STDERR+STDOUT) from each run, each in a new file
with a unique name.

In addition, for each service, there's a `<service_name>.newest.log` symlink,
pointing to the log file for the last run of this service. The creation and
adjustment of this symlink requires the service lock to be held.

If defined in the recipe, a folder exists for each service that contains
symlinks to additional logfiles stored in the service data (for example,
minecraft server logs).

Every now and then, this folder is cleared, a glob search is done in each
service's workdir, and every matching file is symlinked to from here. The global
lock needs to be held during this operation.


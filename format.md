# Beanbag's architecture design!

Beanbag's configuration is a folder, or optionally a zip file of said folder
for efficient deployment. The structure of said folder is as follows

```tree
├ beanbag/
│ ├ beanbag_config.toml
│ ├ addons/ <all addons, to be used in the service code>
│ │ ├ addon_1.toml
│ │ ├ addon_2.toml
│ │ ├ addon_3.toml
│ │ ┆
│ └ services/ <all service descriptions and blobs>
│   ├ service_1.toml
│   ├ service_1.setupfiles/ <all accompanying files for service 1, used exclusively for the provision command and not re-provisioning updates>
│   │ ├ data_file_1.txt
│   │ ├ Caddyfile
│   │ ├ secrets.yml
│   │ ┆
│   ├ service_2.toml
│   ├ service_2.setupfiles/ <all accompanying files for service 2, used exclusively for the provision command and not re-provisioning updates>
│   │ ├ security/
│   │ │ ├ yara_rules.yar
│   │ │ └ id_rsa.pub
│   │ ├ config_file_2.toml
│   │ ┆
│   ├ service_3.toml
│   ┆ 
│ 
└ beans/
    beanbag.lock <empty file used as a mutex to prevent multiple write operations on the beans folder>
    last_provision.json <information on the last provisioning>
    workdirs/ <the folder with the services’ work directories. all logs and datafiles are symlinks to files in these directories>
      service_1/
        <working directory of service 1>
      service_2/
        <working directory of service 2>
      ...
    datafiles/ <the folder with all of the important data; the only directory you need to back up. all of these files are symlinks to files in the workdir>
      service_1/
        <all of service 1’s data files>
      service_2/
        <all of service 2’s data files>
      ...
    logs/ <STDOUT/ERR logs, plus all other log artifacts as symlinks to their respective files in workdirs/>
      service_1.log
      service_1/
        <symlinks to all of service 1’s additional log files. all stored in services/, and are only symlinked to here>
      service_2.log
      ...
    mutexes/ <empty files used as mutexes to prevent double-launching services>
      service_1.lock
      service_2.lock
      ...
```

## Services

```toml
[service]
name="Caddy server"
id="caddy"
envs = { CADDY_ADMIN_INTERFACE_BIND_ADDR = "192.168.2.144:19191" }

[storage]
datafiles = ["db/db.sqlite", "uploads/"] # relative globs
blacklist = ["uploads/cache/"] # relative globs

[logging]
policy = {}# todo
artifacts = ["logs/"] # relative globs, directories ignored
blacklist = ["logs/system.log"] # relative globs, directories ignored

[provision]
commands = [ # commands
  ["download_artifact"]
]

[kill]
envs = { CADDY_SERVER_TOKEN = "@*PD)RKBRSOHIR(BR)S&T" }
commands = [
  ["sh", "caddy stop --config=\"$HOME/Caddyfile\""],
  "killall caddy",
]

[run]
on_exit = "ignore" # or "retry"
envs = { <...> }
commands = [
  <...>
]

[update]
type = "reprovision" # TODO: design other update types.
get_version = { sh = "caddy --version" }
envs = {}
kill_before = true
pre_execute = [
  <...>
]
post_execute = [
  <...>
]
```

## Addons

```toml
[command.download_github_artifact]
usage = "<user/repo> <artifact_filename_regex> <output_path>"
body = [ 
  # Download latest release information
  { set = [
    "releaseinfo",
    { curl = ["-s", ["https://api.github.com/repos/", 1, "/releases/latest"]] }
  ] },
  # Get a matching url, make there is atleast 1 url that matches
  { set = [ "nonce", { jsonquote = { randomstr = "42" } } ] },
  { set = [ "url", { firstline = { jq = [
    ['([.assets[]|select(.name|test(', { jsonquote = 2 }, ')).url]+[', { get = "nonce" }, '])[0]'], # pattern
    { get = "releaseinfo" }
  ] } } ] },
  { assert_neq = [ { get = "nonce" }, { get = "url" }, "No suitable github release found" ] },
  # Download the payload
  { curl = [ "-H", "Accept: application/octet-stream", { get = "url" }, "--output", 3] },
]

```
## Commands syntax

```json
[]
```
<!-- TODO: add examples --> 

A command is a regular JSON array. Its first argument is the name of the
function to be run, and the rest of its arguments are the arguments passed to
the function. If any of the subsequent arguments are also arrays, those are
executed as a command each, and are then substituted with the STDOUT output of
the commands. Nested commands' invocations are logged.

## Standard library

### Execution facilities

* `exec` - Takes an array of command line arguments and executes them. This is a
  special function!
* `[]` - No-op. This is a special function!
<!-- * `seq` - Returns its arguments, concatenated together. Kind of like posix `echo`. -->
  <!-- Has a shorthand form if all arguments are commands: `["seq", ["seq", "hi"], ["exec", "echo", "b"]]` -->
  <!-- is the same as `[["seq", "hi"], ["exec", "echo", "b"]]` --> 
* `sh` - Takes in a shell command as a single string and executes it.
  `["sh", "echo hi"]` is equivalent to `{ exec=[{ get="shell_path" }, "-c", [{}] }`, except
  `"sh"` is replaced with an absolute path to the system's shell.
* `py` - Takes in python code as a single string and executes it.
  `["py", "print(1)"]` is equivalent to `["exec", "python3", "-c", ["cat", ["get", "py_imports"], "print(1)"]]`,
  except `"python3"` is replaced with the system python executable.
* `bc` - Takes in an expression and returns the resulting value. Internally
  expands to `["py", ["cat", "print(", {}, ")"]]`.
* `check` - Takes in a boolean expression and returns yes if it is true, and an
  empty string if it isn't. Internally expands to
  `["py", ["cat", "print('yes') if (", {}, ") else None"]]`
* `sleep` - Takes a (potentially non-whole) number of seconds to wait before
  executing the next logical command. `["sleep", "1.2"]` sleeps for 1 second &
  200 milliseconds. This is a special function!
* `cat` - Concatenates its arguments together. `{ cat = ["2+2=", { bc = "2+2" }] }`
  evaluates to "2+2=4"

### Posix filesystem-like commands

Functionality similar to their respective posix counterparts is provided for the
functions. These will error out if the source or destination paths are not
inside of the work directory. These are all special functions!

<!-- TODO: give examples -->
* `cp` - Copies files and folders into a destination directory. Usage:
  `cp <src> <src> <src> [...] <dest_dir>`.
* `cp_glob` - Same as `cp`, but accepts globs for source files.
* `mv` - Copies files into a destination and removes the original source.
  See `cp` for usage.
* `mv_glob` - see `cp_glob`.
* `rm` - Removes files and empty directories. Does not delete populated folders,
  use `rmr` instead. Usage: `rm <file1> <file2> <file3> [...]`.
* `rmr` - Removes folders recursively. See `rm`.
* `basename` - Finds the parent directory to a path.
* `realpath` - Finds the symlink-traversed path to a directory.
* `find` - Finds the first match for a given glob. Usage: `find <glob>`.
* `find_regex` - Same as `find`, but matches regexes instead of globs.
* `mkdir` - An idempotent directory creation function, similar to unix
  `[ -d <dir> ] || mkdir -- <dir>`. Usage: `mkdir <dir>`.
* `mkdirp` - An idempotent, parent-making directory creation function.
  Similar to unix `mkdir -p -- <dir>`. Usage: `mkdirp <dir>`.
* `touch` - An idempotent file creation function. Similar to unix `touch`.
  Will complain if any of the targets are a directory. Usage:
  `touch <file1> <file2>`.

### Other functions

* `timestamp` - Will be substituted with the unix timestamp. This is a special
  function!
* `datetime` - Will return a user-friendly time/date. This is a special function!
* `echo` - Logs all of its arguments to the root console. This is a special
  function!

### Manipulation

* `jsonpipe` - Takes in a json and outputs a format similar to jsonpipe. Expands
  to some ungodly python one-liner and is run using `py`. Usage:
  `jsonpipe <json> [<separator>]`.
* `jq` - Takes in a jsonquery query and a json, and outputs the result of that
  query.
<!-- TODO: jsonpipe impl: python3 -c 'import json as j, sys as s;U=lambda p,v:lambda:print(p+"\t"+j.dumps(v));a=lambda p, v:{str:U(p,v),bool:U(p,v),float:U(p,v),int:U(p,v),dict:lambda:[a(p+"/"+i,e) for i,e in v.items()],list:lambda:[a(p+"/"+str(i),e) for i,e in enumerate(v)]}[type(v)]();a("",j.load(s.stdin))' -->
* `grep` - Takes in any multiline string and returns the lines that have a
  given regex. `["grep", "\t.*cook", ["jsonpipe", "[1,2,\"cookie\"]"]]` is
  substituted with `/2\t"cookie"`. This is a special function!
* `replace` - Takes in a string, a regex pattern, and a substitute.
  `["replace", "abcde", "b.d", "BcD"]` is substituted with `aBcDe`. This is a
  special function!
* `capture` - Takes in a pattern and a string, and returns every substring that
  matches the pattern in a multiline string. This is a special function!
* `firstline` - Returns the first line of the provided input
* `no_tty_log` - Suppresses log output to the terminal. This method notifies the
  terminal about what its doing to prevent being used to hide code inside
  service files.


### Assertion and formatting

* `is_int` - Asserts that a given string is an integer, and returns that same
  string.
* `is_float` - Asserts that a given string is a float, and returns that same
  string.
* `assert_neq` - Asserts that two values aren't equal
* `shquote` - Quotes its parameters into a valid shell command.
* `pyquote` - If given more than one parameter, quotes its parameters as a valid
  python array of strings. If given only one, quotes its parameter as a valid 
  python string.
* `jsonquote` - If given more than one parameter, quotes its parameters as a
  valid JSON array of strings. If given only one, quotes its parameter as a
  valid JSON string.
* `jsonunquote` - Un-quotes a jsonline input with exclusively json strings

### Networking facilities

* `curl` - Will expand to `["exec", "curl", "-L#f", "--proto", "=https", "--tlsv1.2", "--create-dirs", {}]`
* `download_github_artifact` - Will download a latest github release artifact
  from a repo name (in the format `user/repo`), a regex that matches the desired
  artifact's name, and an output path.
  `{ download_github_artifact = ['dunglas/frankenphp', ['frankenphp-linux-', { get = "arch" }, '-gnu'], './caddy'] }`
  downloads the latest release of FrankenPHP into `./caddy`
<!-- TODO: do networking -->

### Cryptographic facilities

* `unvault` - Decrypts a vault <!-- TODO: figure this out -->
* `randomstr` - Generates a string with alphanumeric characters of a provided
  length, (default 40.) `["randomstr", 20]` can turn into `A01LT7XRDaIZKLaQdjqs`. First letter
  is guaranteed to not be a number.
<!-- * `randomint` - Generates a random integer from zero to a provided maximum, or -->
  <!-- 340282366920938463463374607431768211455. -->

### Variable set-get

Variables modified using these functions are scoped for each function call, and
are only accessible within beanbag.

* `set` - Set the value of a variable to be retreived with `get`:
  `["set", "version", "1.45.3"]` sets the variable `version` to `1.45.3`. This
  is a special function!
* `set_global` - Like `set`, but stores the variable in the global scope instead.
  This is a special function!
* `get` - Is substituted with the variable it references:
  `[["set", "version", "1.45.3"], ["get", "version"]]` evaluates to `1.45.3`.
  This is a special function!
* `get_global` - Like `get`, but traverses the scope in reverse and finds the
  first definition of a variable. This is a special function!
* `get_vault` - Retrieves an encrypted variable with a key prompted through a
  command-line setting. Internally expands to `["unvault", ["get", 1]]`.

There are some immutable built-in global variables:

| name | description | example value |
|---|---|---|
|`py_imports`| A few useful python imports, all imported like `from <package> import *`. Terminated with a newline. | `from math import *; from json import loads, dumps; [...] \n` |
|`py_exec`| Absolute path to the `python3` executable as reported by `sys.executable` | `/home/linuxbrew/.linuxbrew/opt/python@3.13/bin/python3.13` |
|`shell_path`| Absolute path to the system shell. As reported by the `/etc/pwd` database, or through `which bash` then `which shell`. | `/usr/bin/zsh` |
|*all config variables*| Every variable defined in the config under `config.defines`, `service.defines` and `[run/kill/update].defines` | `KEY:aafdf4ba22c84e3829cf1d58587b5b10` |
|`username`| Result of `whoami` | `jackblack` |
|`bin_path`| Location where beanbag's accompanying binaries are stored | `/home/jackblack/maintenance/beanbag/bins/` |
|`arch`| Result of `os.uname().machine` | `x86_64`|
|`arch_names`| Regex pattern to match alternative architecture names, or just `arch` if found none| `amd64|x86[-_\s]64` |
|`os`| Result of `sys.platform` | `linux`|
|`nodename`| Result of `os.uname().nodename`| `jackblack-pc` |

<!-- TODO: implement all global variables -->

# Configuration

Beanbag's configuration (called the recipe book) is a folder, or optionally a
zip file of said folder. A comprehensive example of this folder structure is as
follows:

```tree
recipes/
├ beanbag_config.toml
├ library/ <all command libraries, to be used in service descriptions>
│ ├ library_1.toml
│ ├ library_2.toml
│ ├ library_3.toml
│ ┆
└ services/ <all service descriptions and blobs>
  ├ service_1.toml
  ├ service_1.setupfiles/ <extra files used for provisioning service 1>
  │ ├ data_file_1.txt
  │ ├ Caddyfile
  │ ├ secrets.yml
  │ ┆
  ├ service_2.toml
  ├ service_2.setupfiles/ <extra files used for provisioning service 2>
  │ ├ security/
  │ │ ├ yara_rules.yar
  │ │ └ id_rsa.pub
  │ ├ config_file_2.toml
  │ ┆
  ├ service_3.toml
  ┆ 
```

The rest of this page documents each sub directory.

## `beanbag_config.toml`

TODO: Write beanbag config description and link to scheme
TODO: write scheme documentation for beanbag_config.toml

## `library/`

The library folder contains libraries that add reusable subroutines for all
services. Libraries may have dependencies on routines from other libraries. Each
libary is a toml file, and the scheme is found
[here](beanbag-library-scheme.md).

TODO: write beanbag-library-scheme.md

## `services/`

The service directory contains each service to be run. Services can't depend
on eachother, but they can use routines from
[libraries](beanbag.md#`services/`). Each service is defined by a TOML file and
extra setup files. The scheme for the TOML file is found
[here](beanbag-service-scheme.md).

TODO: write beanbag-service-scheme.md

At provision time, if the service is accompanied by a `.setupfiles` folder,
the contents of the setupfiles folder are copied to the work directory. The
purpose of the setupfiles is to include any configuration files that the service
may need.






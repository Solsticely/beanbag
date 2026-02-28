# Overview

Beanbag's configuration (called the recipe book) is a folder, or optionally a
zip file of said folder. A comprehensive example of this folder structure is as
follows:

```tree
recipes/
├ beanbag_config.toml
├ addons/ <all addons, to be used in service descriptions>
│ ├ addon_1.toml
│ ├ addon_2.toml
│ ├ addon_3.toml
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

Each service, like your webserver and your database, is configured in the
`services/` directory.

Addons are stored in the `addon/` directory. Each addon contains reusable
snippets of code (as functions) that can be used in other addons, or services.

The rest of this page documents each sub directory.

## `beanbag_config.toml`

TODO: Write beanbag config description and link to scheme
TODO: write scheme documentation for beanbag_config.toml

## `addons/`

The addon folder contains addons that add reusable subroutines that can be used
in services and in other addons. Each addon is a toml file, and the scheme is
found [here](beanbag-addon-scheme.md).

TODO: write beanbag-addon-scheme.md

## `services/`

The service directory contains each service to be run. Services can't depend
on eachother, but they can use routines from
[addons](beanbag.md#`services/`). Each service is defined by a TOML file and
extra setup files. The scheme for the TOML file is found
[here](beanbag-service-scheme.md).

TODO: write beanbag-service-scheme.md

At provision time, if the service is accompanied by a `.setupfiles` folder,
the contents of the setupfiles folder are copied to the work directory. The
purpose of the setupfiles is to include any configuration files that the service
may need.






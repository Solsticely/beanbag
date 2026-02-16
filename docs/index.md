# Welcome to the BeanBag Documentation!

Beanbag is a server provisioning and service running tool, intended to be ran
exclusively in user-space :>

This documentation serves the purpose of reminding me how the tool works :)

## Terminology

- **Service** A service, like systemd's services. If you use beanbag to run your
homeserver, each app you self-host is called a service. <br/>Unlike systemd,
*beanbag can update your services for you,* reducing maintenance
cost by quite a bit.
- **Recipe book (a folder/file)** The entire configuration folder for all
services, containing each recipe.
- **Recipe (a TOML/TOML+folder/zip file)** The configuration for a single service. Each recipe
is a TOML file with an optional folder containing config files for the service
binary itself (e.g. a caddyfile for caddy). Optionally, it can also be a zip of
the TOML file and the folder together. <br/> Each recipe defines a
way to *provision*, *run*, *kill*, and *update* a service.
- **Beans (folder)** A provisioned configuration.
- **Updating** Updates each service, downloading new versions of binaries, 
- **Persistent data** All files that a service always needs to run. All user
data that is intended to be persistent between runs would fall under this
category.

## Quick start

Acquire a recipe folder first :)

* `beanbag provision recipes.zip && beanbag run recipes.zip`

That's it! you're now a proud owner of a provisioned homeserver :D

When new versions of your services are out, just run `beanbag update` to
automatically update them.


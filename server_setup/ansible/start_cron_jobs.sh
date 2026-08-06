#!/usr/bin/env bash
set -euxo pipefail
# NOTE: IMPORTANT: This file is a JINJA template
# NOTE: IMPORTANT: This file SHOULD NOT generate output as it is a cron job

# Relevant available variables:
# - cron_scripts_path ('Monthly', 'Hourly', etc.)
# - new_user_name ('tom_scott')
# Paths are /home/{{ new_user_name }}/{secure/,}Crons/{{ cron_scripts_path }}

# TODO: logs should be at /home/{{ new_user_name }}/{secure/,}Logs/Cron/run_%date%_{{ cron_scripts_path }}_%script_name%.txt
# TODO: run all scripts as root            from /home/{{ new_user_name }}/secure/Crons/{{ cron_scripts_path }} EXCEPT this script
# TODO: run all scripts as {{ new_user_name }} from /home/{{ new_user_name }}/Crons/{{ cron_scripts_path }}


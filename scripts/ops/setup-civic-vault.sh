#!/bin/sh
# Only this wrapper runs in the shell; all secret input stays inside Python.
set +x
set +v
set -eu
umask 077
ulimit -c 0

repo=/home/seanr/dev/let-food-into-civic
python="$repo/venv/bin/python"
helper="$repo/scripts/ops/provision_relay_config.py"

if [ "$#" -gt 1 ]; then
    echo 'Usage: setup-civic-vault.sh [--check]. Never pass credentials as arguments.' >&2
    exit 2
fi
if [ "$#" -eq 1 ]; then
    if [ "$1" != '--check' ]; then
        echo 'Only --check is accepted. Never pass credentials as arguments.' >&2
        exit 2
    fi
    exec "$python" -I "$helper" --check
fi
if [ ! -t 0 ] || [ ! -t 1 ]; then
    echo 'Run directly in your private interactive SSH terminal; do not pipe input or output.' >&2
    exit 2
fi
if [ ! -x "$python" ] || [ ! -r "$helper" ]; then
    echo 'Civic Python environment or provisioning helper is unavailable.' >&2
    exit 1
fi
exec "$python" -I "$helper"

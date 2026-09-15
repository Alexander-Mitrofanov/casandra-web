#!/usr/bin/env bash
set -euo pipefail
exec /srv/casandra/releases/backend/current/venv/bin/python -I -B \
    -m casandra_web.model_switch "$@"

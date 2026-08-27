#!/usr/bin/env bash
set -euo pipefail

umask 077
[[ $# -eq 1 ]] || {
    echo "usage: $0 https://pages-origin.example" >&2
    exit 64
}
[[ ${EUID} -eq 0 ]] || {
    echo "prepare-host.sh must run as root" >&2
    exit 77
}

pages_origin=$1
/usr/bin/python3 - "${pages_origin}" <<'PY'
import sys
from urllib.parse import urlsplit

value = sys.argv[1]
parsed = urlsplit(value)
if (
    parsed.scheme != "https"
    or not parsed.hostname
    or parsed.path
    or parsed.query
    or parsed.fragment
    or parsed.username
    or parsed.password
    or value.endswith("/")
):
    raise SystemExit("Pages origin must be an exact HTTPS origin without a trailing slash")
PY

script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
/usr/bin/install -d -o root -g root -m 0755 /srv/casandra
/usr/bin/install -d -o root -g root -m 0700 /srv/casandra/config
/usr/bin/install -d -o 10001 -g 10001 -m 0700 /srv/casandra/jobs
/usr/bin/install -d -o 10001 -g 10001 -m 0700 /srv/casandra/tmp

if [[ ! -f /srv/casandra/config/casandra-web.env ]]; then
    pepper=$(/usr/bin/openssl rand -hex 32)
    /usr/bin/awk -v origin="${pages_origin}" -v pepper="${pepper}" '
        { gsub(/__PAGES_ORIGIN__/, origin); gsub(/__GENERATED_TOKEN_PEPPER__/, pepper); print }
    ' "${script_root}/casandra-web.env.example" > /srv/casandra/config/casandra-web.env
fi
[[ -f /srv/casandra/config/casandra-web.env \
    && ! -L /srv/casandra/config/casandra-web.env ]] || {
    echo "rendered environment must be a regular file" >&2
    exit 78
}
if /usr/bin/grep -Eq '__PAGES_ORIGIN__|__GENERATED_TOKEN_PEPPER__' \
    /srv/casandra/config/casandra-web.env; then
    echo "rendered environment still contains a placeholder" >&2
    exit 78
fi
/usr/bin/chown root:root /srv/casandra/config/casandra-web.env
/usr/bin/chmod 0600 /srv/casandra/config/casandra-web.env
/usr/bin/install -o root -g root -m 0644 "${script_root}/compose.yml" /srv/casandra/compose.yml

echo "Prepared /srv/casandra. No container was started."
echo "Review the environment, build the image, and then start the compose project explicitly."

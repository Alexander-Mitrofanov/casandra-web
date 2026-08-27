#!/usr/bin/env bash
set -euo pipefail

umask 077

usage() {
    echo "usage: $0 /absolute/path/to/WebServer https://pages-origin.example" >&2
    exit 64
}

[[ $# -eq 2 ]] || usage
[[ ${EUID} -eq 0 ]] || {
    echo "install-service.sh must run as root" >&2
    exit 77
}

source_root=$1
pages_origin=$2
[[ ${source_root} = /* ]] || {
    echo "WebServer source path must be absolute" >&2
    exit 64
}
source_root=$(readlink -f -- "${source_root}")
[[ -f ${source_root}/backend/pyproject.toml ]] || {
    echo "backend/pyproject.toml is missing from the WebServer source" >&2
    exit 66
}
[[ -f ${source_root}/deploy/casandra-web.env.example ]] || {
    echo "deployment templates are missing from the WebServer source" >&2
    exit 66
}

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

for command in /usr/bin/python3.10 /usr/bin/openssl /usr/bin/systemctl /usr/bin/tar /usr/bin/sha256sum; do
    [[ -x ${command} ]] || {
        echo "required program is unavailable: ${command}" >&2
        exit 69
    }
done

casandra_command=/srv/casandra/releases/scientific/current/casandra/bin/casandra
identify_command=/srv/casandra/releases/scientific/current/integration/bin/crispr-tools
identify_launcher=/srv/casandra/releases/scientific/current/crispridentify/bin/run-crispridentify
for command in "${casandra_command}" "${identify_command}" "${identify_launcher}"; do
    [[ -x ${command} && ! -L ${command} ]] || {
        echo "verified scientific executable is unavailable: ${command}" >&2
        exit 69
    }
done

if ! getent group casandrasvc >/dev/null; then
    /usr/sbin/groupadd --system casandrasvc
fi
if ! getent passwd casandrasvc >/dev/null; then
    /usr/sbin/useradd --system --gid casandrasvc --home-dir /nonexistent \
        --shell /usr/sbin/nologin casandrasvc
fi

/usr/bin/install -d -o root -g root -m 0755 /srv/casandra
/usr/bin/install -d -o root -g root -m 0755 /srv/casandra/releases
/usr/bin/install -d -o root -g root -m 0755 /srv/casandra/releases/backend
/usr/bin/install -d -o casandrasvc -g casandrasvc -m 0700 /srv/casandra/jobs
/usr/bin/install -d -o www-data -g www-data -m 0700 /srv/casandra/nginx-client-body

if [[ ! -f /etc/casandra-web-runners.json ]]; then
    /usr/bin/install -o root -g casandrasvc -m 0640 \
        "${source_root}/deploy/casandra-web-runners.json.example" \
        /etc/casandra-web-runners.json
fi
[[ -f /etc/casandra-web-runners.json && ! -L /etc/casandra-web-runners.json ]] || {
    echo "/etc/casandra-web-runners.json must be a regular file" >&2
    exit 78
}
/usr/bin/chown root:casandrasvc /etc/casandra-web-runners.json
/usr/bin/chmod 0640 /etc/casandra-web-runners.json

backend_digest=$(
    cd "${source_root}/backend"
    {
        /usr/bin/sha256sum pyproject.toml
        find src/casandra_web -type f -name '*.py' -print0 \
            | sort -z \
            | xargs -0 /usr/bin/sha256sum
    } | /usr/bin/sha256sum | cut -d' ' -f1
)
release_id=${backend_digest:0:24}
release_root=/srv/casandra/releases/backend/${release_id}

if [[ ! -d ${release_root} ]]; then
    /usr/bin/install -d -o root -g root -m 0755 "${release_root}/source"
    cleanup_release=${release_root}
    trap 'if [[ -n ${cleanup_release:-} && ${cleanup_release} == /srv/casandra/releases/backend/* ]]; then rm -rf -- "${cleanup_release}"; fi' EXIT
    /usr/bin/tar -C "${source_root}/backend" \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' --exclude='*.egg-info' \
        -cf - pyproject.toml src \
        | /usr/bin/tar -C "${release_root}/source" -xf -
    /usr/bin/python3.10 -m venv "${release_root}/venv"
    pip_args=(--disable-pip-version-check --no-cache-dir)
    if [[ -n ${CASANDRA_WEB_WHEELHOUSE:-} ]]; then
        [[ ${CASANDRA_WEB_WHEELHOUSE} = /* && -d ${CASANDRA_WEB_WHEELHOUSE} ]] || {
            echo "CASANDRA_WEB_WHEELHOUSE must be an existing absolute directory" >&2
            exit 64
        }
        pip_args+=(--no-index --find-links "${CASANDRA_WEB_WHEELHOUSE}")
    fi
    "${release_root}/venv/bin/pip" install "${pip_args[@]}" "${release_root}/source"
    /usr/bin/chown -R root:root "${release_root}"
    /usr/bin/chmod -R go-w "${release_root}"
    cleanup_release=
    trap - EXIT
fi

current_link=/srv/casandra/releases/backend/current
temporary_link=/srv/casandra/releases/backend/.current.$$
/usr/bin/ln -s "${release_root}" "${temporary_link}"
/usr/bin/mv -Tf "${temporary_link}" "${current_link}"

if [[ ! -f /etc/casandra-web.env ]]; then
    pepper=$(/usr/bin/openssl rand -hex 32)
    /usr/bin/awk -v origin="${pages_origin}" -v pepper="${pepper}" '
        { gsub(/__PAGES_ORIGIN__/, origin); gsub(/__GENERATED_TOKEN_PEPPER__/, pepper); print }
    ' "${source_root}/deploy/casandra-web.env.example" > /etc/casandra-web.env
fi
[[ -f /etc/casandra-web.env && ! -L /etc/casandra-web.env ]] || {
    echo "/etc/casandra-web.env must be a regular file" >&2
    exit 78
}
if /usr/bin/grep -Eq '__PAGES_ORIGIN__|__GENERATED_TOKEN_PEPPER__' /etc/casandra-web.env; then
    echo "/etc/casandra-web.env still contains a placeholder" >&2
    exit 78
fi
/usr/bin/chown root:casandrasvc /etc/casandra-web.env
/usr/bin/chmod 0640 /etc/casandra-web.env

for unit in casandra-web-api.service casandra-web-worker.service \
    casandra-web-cleanup.service casandra-web-cleanup.timer; do
    /usr/bin/install -o root -g root -m 0644 \
        "${source_root}/deploy/systemd/${unit}" "/etc/systemd/system/${unit}"
done

/usr/bin/install -o root -g root -m 0644 \
    "${source_root}/deploy/nginx/casandra-api-http.conf" \
    /etc/nginx/conf.d/casandra-api-http.conf
/usr/bin/install -d -o root -g root -m 0755 /etc/nginx/snippets
/usr/bin/install -o root -g root -m 0644 \
    "${source_root}/deploy/nginx/casandra-api-location.conf" \
    /etc/nginx/snippets/casandra-api-location.conf

/usr/bin/systemctl daemon-reload
/usr/bin/systemctl enable casandra-web-api.service casandra-web-worker.service \
    casandra-web-cleanup.timer
/usr/bin/systemctl restart casandra-web-api.service casandra-web-worker.service
/usr/bin/systemctl start casandra-web-cleanup.timer

echo "Installed CasAndra Web backend release ${release_id}."
echo "Include /etc/nginx/snippets/casandra-api-location.conf in the HTTPS server, then run verify-deployment.sh."

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
[[ -f ${source_root}/backend/pyproject.toml \
    && ! -L ${source_root}/backend/pyproject.toml ]] || {
    echo "backend/pyproject.toml is missing from the WebServer source" >&2
    exit 66
}
[[ -f ${source_root}/deploy/casandra-web.env.example \
    && ! -L ${source_root}/deploy/casandra-web.env.example ]] || {
    echo "deployment templates are missing from the WebServer source" >&2
    exit 66
}
wheel_builder=${source_root}/deploy/rebuild-backend-wheel.py
[[ -f ${wheel_builder} && ! -L ${wheel_builder} ]] || {
    echo "offline backend wheel builder is missing from the WebServer source" >&2
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

for command in /usr/bin/openssl /usr/bin/python3 /usr/bin/systemctl \
    /usr/bin/tar /usr/bin/sha256sum /usr/sbin/nginx; do
    [[ -x ${command} ]] || {
        echo "required program is unavailable: ${command}" >&2
        exit 69
    }
done
[[ $(/usr/bin/python3 -I -B -S -c 'import sys; print("%d.%d" % sys.version_info[:2])') == 3.12 ]] || {
    echo "the standalone profile requires Ubuntu Python 3.12" >&2
    exit 69
}
[[ $(/usr/bin/findmnt -n -o TARGET -T /srv/casandra) == /srv/casandra ]] || {
    echo "/srv/casandra must be a dedicated mount" >&2
    exit 78
}

scientific_id=178f45ddd4080e30774d9e92d913a35088e253c24116e7149d6859639278ff42
scientific_root=/srv/crispr/software/releases/scientific/${scientific_id}
scientific_verifier=/opt/crispr-suite/deployment/scientific/verify-scientific-release.py
[[ -f ${scientific_verifier} && ! -L ${scientific_verifier} \
    && $(/usr/bin/sha256sum "${scientific_verifier}" | /usr/bin/cut -d' ' -f1) \
       == fdfa7fa1c6c9ac54bf126220637028494497954411e51dd0a4fed2f96a703a8f ]] || {
    echo "the attested scientific-release verifier is unavailable" >&2
    exit 69
}
/usr/bin/python3 -I -B -S "${scientific_verifier}" \
    --manifest /etc/crispr-tools/release-manifest.json \
    --expected-sha256 "${scientific_id}" --require-current >/dev/null

identify_command=/opt/crispr-workers/integration/bin/crispr-tools
identify_launcher=/usr/local/libexec/crispr-web/run-crispridentify
for command in "${identify_command}" "${identify_launcher}"; do
    [[ -x ${command} && ! -L ${command} ]] || {
        echo "verified scientific executable is unavailable: ${command}" >&2
        exit 69
    }
done
[[ $(${identify_command} --version) == 'crispr-tools 0.2.6' ]] || {
    echo "Integration version is not the reviewed release" >&2
    exit 69
}
[[ $(/usr/bin/sha256sum "${identify_launcher}" | /usr/bin/cut -d' ' -f1) \
    == c3750da26aa56a620365ec489e7aab2777d326b728a565d74335cf0c623a7ad4 ]] || {
    echo "CRISPRidentify wrapper differs from the reviewed release" >&2
    exit 69
}

wheelhouse=${CASANDRA_WEB_WHEELHOUSE:-/srv/casandra/staging/c73be92c23c44815d51c961995018dfe796518bf0ace68b05096dd030947d607/wheelhouse}
[[ ${wheelhouse} = /* && -d ${wheelhouse} && ! -L ${wheelhouse} ]] || {
    echo "CASANDRA_WEB_WHEELHOUSE must be an existing absolute directory" >&2
    exit 64
}
wheelhouse=$(readlink -e -- "${wheelhouse}")
wheel_manifest=$(dirname -- "${wheelhouse}")/SHA256SUMS
[[ -f ${wheel_manifest} && ! -L ${wheel_manifest} \
    && $(/usr/bin/sha256sum "${wheel_manifest}" | /usr/bin/cut -d' ' -f1) \
       == c73be92c23c44815d51c961995018dfe796518bf0ace68b05096dd030947d607 ]] || {
    echo "offline wheel manifest differs from the reviewed release" >&2
    exit 65
}
(
    cd "$(dirname -- "${wheelhouse}")"
    /usr/bin/sha256sum --check --strict SHA256SUMS >/dev/null
) || {
    echo "offline wheelhouse verification failed" >&2
    exit 65
}

backend_release_digest() {
    local backend_root=$1
    (
        cd "${backend_root}"
        {
            printf 'casandra-web-standalone-backend-v2\0'
            printf '%s\0' \
                c73be92c23c44815d51c961995018dfe796518bf0ace68b05096dd030947d607
            /usr/bin/sha256sum --zero pyproject.toml
            /usr/bin/find src/casandra_web -type f -name '*.py' -print0 \
                | LC_ALL=C /usr/bin/sort -z \
                | /usr/bin/xargs -0 -r /usr/bin/sha256sum --zero
        } | /usr/bin/sha256sum | /usr/bin/cut -d' ' -f1
    )
}

python_source_manifest() {
    local package_parent=$1
    [[ -d ${package_parent}/casandra_web && ! -L ${package_parent}/casandra_web ]] \
        || return 1
    [[ -z $(/usr/bin/find "${package_parent}/casandra_web" -type l -print -quit) ]] \
        || return 1
    (
        cd "${package_parent}"
        /usr/bin/find casandra_web -type f -name '*.py' -print0 \
            | LC_ALL=C /usr/bin/sort -z \
            | /usr/bin/xargs -0 -r /usr/bin/sha256sum --zero
    )
}

verify_backend_release() {
    local candidate=$1
    local expected_digest=$2
    local candidate_digest site_packages module_file release_value
    [[ -d ${candidate} && ! -L ${candidate} \
        && -f ${candidate}/source/pyproject.toml \
        && ! -L ${candidate}/source/pyproject.toml \
        && -f ${candidate}/release.env && ! -L ${candidate}/release.env \
        && -x ${candidate}/venv/bin/python ]] \
        || return 1
    [[ -z $(/usr/bin/find "${candidate}/source/src/casandra_web" -type l -print -quit) ]] \
        || return 1
    [[ -n $(/usr/bin/find "${candidate}/source/src/casandra_web" \
        -type f -name '*.py' -print -quit) ]] || return 1
    [[ -z $(/usr/bin/find "${candidate}/source/src/casandra_web" \
        -type f ! -name '*.py' -print -quit) ]] || return 1
    candidate_digest=$(backend_release_digest "${candidate}/source")
    [[ ${candidate_digest} == "${expected_digest}" ]] || return 1
    [[ $(/usr/bin/wc -l < "${candidate}/release.env") -eq 1 ]] || return 1
    release_value=$(<"${candidate}/release.env")
    [[ ${release_value} == "CASANDRA_WEB_RELEASE_ID=${expected_digest}" ]] || return 1
    site_packages=$(
        "${candidate}/venv/bin/python" -I -B -c \
            'import sysconfig; print(sysconfig.get_path("purelib"))'
    )
    site_packages=$(readlink -e -- "${site_packages}")
    [[ -n ${site_packages} && ${site_packages} == "${candidate}/venv/"* ]] || return 1
    [[ -d ${site_packages}/casandra_web && ! -L ${site_packages}/casandra_web ]] \
        || return 1
    [[ -z $(/usr/bin/find "${site_packages}/casandra_web" -type l -print -quit) ]] \
        || return 1
    [[ -n $(/usr/bin/find "${site_packages}/casandra_web" \
        -type f -name '*.py' -print -quit) ]] || return 1
    [[ -z $(/usr/bin/find "${site_packages}/casandra_web" \
        -type f ! -name '*.py' -print -quit) ]] || return 1
    /usr/bin/cmp -s \
        <(python_source_manifest "${candidate}/source/src") \
        <(python_source_manifest "${site_packages}") \
        || return 1
    module_file=$(
        "${candidate}/venv/bin/python" -I -B -c \
            'import casandra_web; print(casandra_web.__file__)'
    )
    [[ $(readlink -e -- "${module_file}") \
        == "${site_packages}/casandra_web/__init__.py" ]] || return 1
    "${candidate}/venv/bin/python" -I -B -m pip --isolated check >/dev/null
}

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
/usr/bin/install -d -o casandrasvc -g casandrasvc -m 0700 /srv/casandra/tmp
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

[[ -z $(/usr/bin/find "${source_root}/backend/src/casandra_web" -type l -print -quit) ]] || {
    echo "backend Python source must not contain symbolic links" >&2
    exit 65
}
backend_digest=$(backend_release_digest "${source_root}/backend")
release_id=${backend_digest:0:24}
release_root=/srv/casandra/releases/backend/${release_id}
template_web_wheel=${wheelhouse}/casandra_web-0.1.0-py3-none-any.whl
[[ -f ${template_web_wheel} && ! -L ${template_web_wheel} ]] || {
    echo "reviewed backend metadata wheel is unavailable" >&2
    exit 65
}
mapfile -d '' -t candidate_web_wheels < <(
    /usr/bin/find "${wheelhouse}" -maxdepth 1 -name 'casandra_web-*.whl' -print0
)
[[ ${#candidate_web_wheels[@]} -eq 1 \
    && ${candidate_web_wheels[0]} == "${template_web_wheel}" ]] || {
    echo "offline wheelhouse must contain exactly one reviewed backend wheel" >&2
    exit 65
}

if [[ ! -d ${release_root} ]]; then
    /usr/bin/install -d -o root -g root -m 0755 "${release_root}/source"
    cleanup_release=${release_root}
    trap 'if [[ -n ${cleanup_release:-} && ${cleanup_release} == /srv/casandra/releases/backend/* ]]; then rm -rf -- "${cleanup_release}"; fi' EXIT
    /usr/bin/tar -C "${source_root}/backend" \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' --exclude='*.egg-info' \
        -cf - pyproject.toml src \
        | /usr/bin/tar -C "${release_root}/source" -xf -
    /usr/bin/python3 -m venv "${release_root}/venv"
    "${release_root}/venv/bin/python" -I -B -m pip --isolated install \
        --disable-pip-version-check --no-cache-dir --no-index \
        --only-binary=:all: --find-links "${wheelhouse}" \
        CasAndra==0.3.0.dev0 fastapi==0.139.2 pydantic==2.13.4 \
        'uvicorn[standard]==0.51.0'
    rebuilt_web_wheel=${release_root}/casandra_web-0.1.0-py3-none-any.whl
    /usr/bin/python3 -I -B -S "${wheel_builder}" \
        --template "${template_web_wheel}" --source "${release_root}/source" \
        --output "${rebuilt_web_wheel}"
    "${release_root}/venv/bin/python" -I -B -m pip --isolated install \
        --disable-pip-version-check --no-cache-dir --no-compile --no-index --no-deps \
        "${rebuilt_web_wheel}"
    printf 'CASANDRA_WEB_RELEASE_ID=%s\n' "${backend_digest}" \
        > "${release_root}/release.env"
    "${release_root}/venv/bin/python" -I -B -m pip --isolated check
    /usr/bin/chown -R root:root "${release_root}"
    /usr/bin/chmod -R a+rX,go-w "${release_root}"
    /usr/bin/chmod 0644 "${release_root}/release.env"
    verify_backend_release "${release_root}" "${backend_digest}" || {
        echo "new backend release failed source/install attestation" >&2
        exit 65
    }
    cleanup_release=
    trap - EXIT
else
    verify_backend_release "${release_root}" "${backend_digest}" || {
        echo "existing backend release failed source/install attestation" >&2
        exit 65
    }
fi
/usr/bin/chown -R root:root "${release_root}"
/usr/bin/chmod -R a+rX,go-w "${release_root}"
/usr/bin/chmod 0644 "${release_root}/release.env"

casandra_command=${release_root}/venv/bin/casandra
[[ $(${casandra_command} --version) == 'casandra 0.3.0.dev0' ]] || {
    echo "CasAndra version is not the reviewed release" >&2
    exit 69
}
"${casandra_command}" inspect-model >/dev/null

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
/usr/bin/install -d -o root -g root -m 0755 /etc/nginx/sites-available /etc/nginx/sites-enabled
/usr/bin/install -o root -g root -m 0644 \
    "${source_root}/deploy/nginx/casandra-standalone.conf" \
    /etc/nginx/sites-available/casandra-standalone.conf
if [[ -L /etc/nginx/sites-enabled/default ]]; then
    [[ $(readlink -- /etc/nginx/sites-enabled/default) == /etc/nginx/sites-available/default ]] || {
        echo "refusing to replace an unexpected Nginx default-site link" >&2
        exit 78
    }
    /usr/bin/rm -- /etc/nginx/sites-enabled/default
elif [[ -e /etc/nginx/sites-enabled/default ]]; then
    echo "refusing to replace an unexpected Nginx default site" >&2
    exit 78
fi
if [[ ! -e /etc/nginx/sites-enabled/casandra-standalone.conf \
    && ! -L /etc/nginx/sites-enabled/casandra-standalone.conf ]]; then
    /usr/bin/ln -s /etc/nginx/sites-available/casandra-standalone.conf \
        /etc/nginx/sites-enabled/casandra-standalone.conf
fi
/usr/sbin/nginx -t

current_link=/srv/casandra/releases/backend/current
temporary_link=/srv/casandra/releases/backend/.current.$$
if [[ -e ${current_link} || -L ${current_link} ]]; then
    [[ -L ${current_link} \
        && $(readlink -e -- "${current_link}") \
           =~ ^/srv/casandra/releases/backend/[0-9a-f]{24}$ ]] || {
        echo "refusing to replace an unexpected backend current target" >&2
        exit 78
    }
fi
/usr/bin/ln -s "${release_root}" "${temporary_link}"
/usr/bin/mv -Tf "${temporary_link}" "${current_link}"
/usr/bin/systemctl daemon-reload
/usr/bin/systemctl enable casandra-web-api.service casandra-web-worker.service \
    casandra-web-cleanup.timer
/usr/bin/systemctl reset-failed casandra-web-api.service casandra-web-worker.service
/usr/bin/systemctl restart casandra-web-api.service casandra-web-worker.service
/usr/bin/systemctl start casandra-web-cleanup.timer
/usr/bin/systemctl unmask nginx.service
/usr/bin/systemctl enable nginx.service
/usr/bin/systemctl restart nginx.service

echo "Installed CasAndra Web backend release ${release_id}."
echo "Started the private API, worker, cleanup timer, and loopback-only Nginx edge."

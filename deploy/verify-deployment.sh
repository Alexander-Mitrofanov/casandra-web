#!/usr/bin/env bash
set -euo pipefail

[[ ${EUID} -eq 0 ]] || {
    echo "verify-deployment.sh must run as root" >&2
    exit 77
}

fail() {
    echo "verification failed: $*" >&2
    exit 1
}

[[ -f /etc/casandra-web.env && ! -L /etc/casandra-web.env ]] \
    || fail "/etc/casandra-web.env is not a regular file"
[[ -f /etc/casandra-web-runners.json && ! -L /etc/casandra-web-runners.json ]] \
    || fail "/etc/casandra-web-runners.json is not a regular file"
[[ $(stat -c '%U:%G:%a' /etc/casandra-web.env) == root:casandrasvc:640 ]] \
    || fail "/etc/casandra-web.env ownership or mode is incorrect"
[[ $(stat -c '%U:%G:%a' /etc/casandra-web-runners.json) == root:casandrasvc:640 ]] \
    || fail "runner configuration ownership or mode is incorrect"
if grep -Eq '__PAGES_ORIGIN__|__GENERATED_TOKEN_PEPPER__' /etc/casandra-web.env; then
    fail "the environment contains an unresolved placeholder"
fi

[[ $(stat -c '%U:%G:%a' /srv/casandra/jobs) == casandrasvc:casandrasvc:700 ]] \
    || fail "job root ownership or mode is incorrect"
[[ -L /srv/casandra/releases/backend/current ]] \
    || fail "backend current release link is missing"

for command in \
    /srv/casandra/releases/backend/current/venv/bin/casandra-web-api \
    /srv/casandra/releases/backend/current/venv/bin/casandra-web-worker \
    /srv/casandra/releases/backend/current/venv/bin/casandra-web-cleanup \
    /srv/casandra/releases/scientific/current/casandra/bin/casandra \
    /srv/casandra/releases/scientific/current/integration/bin/crispr-tools \
    /srv/casandra/releases/scientific/current/crispridentify/bin/run-crispridentify; do
    [[ -x ${command} ]] || fail "required executable is unavailable: ${command}"
done

systemd-analyze verify \
    /etc/systemd/system/casandra-web-api.service \
    /etc/systemd/system/casandra-web-worker.service \
    /etc/systemd/system/casandra-web-cleanup.service \
    /etc/systemd/system/casandra-web-cleanup.timer >/dev/null

for unit in casandra-web-api.service casandra-web-worker.service casandra-web-cleanup.timer; do
    systemctl is-enabled --quiet "${unit}" || fail "${unit} is not enabled"
    systemctl is-active --quiet "${unit}" || fail "${unit} is not active"
done

listener=$(ss -H -ltn 'sport = :8010')
[[ -n ${listener} ]] || fail "nothing is listening on port 8010"
if grep -Evq '127\.0\.0\.1:8010[[:space:]]' <<<"${listener}"; then
    fail "port 8010 has a non-loopback listener"
fi

nginx -t >/dev/null

health_url=http://127.0.0.1:8010/casandra/api/v1/health
config_url=http://127.0.0.1:8010/casandra/api/v1/config
version_url=http://127.0.0.1:8010/casandra/api/v1/version
temporary_root=$(mktemp -d /tmp/casandra-web-verify.XXXXXX)
trap 'rm -rf -- "${temporary_root}"' EXIT

healthy=false
for _attempt in 1 2 3 4 5 6 7 8 9 10; do
    if curl --fail --silent --show-error --max-time 5 "${health_url}" \
        --output "${temporary_root}/health.json"; then
        if /usr/bin/python3 - "${temporary_root}/health.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle)
if value.get("status") != "ok" or value.get("database") != "ok" or value.get("worker") != "ok":
    raise SystemExit(1)
PY
        then
            healthy=true
            break
        fi
    fi
    sleep 2
done
[[ ${healthy} == true ]] || fail "API or worker health did not become ready"

curl --fail --silent --show-error --max-time 5 "${config_url}" \
    --output "${temporary_root}/config.json"
curl --fail --silent --show-error --max-time 5 "${version_url}" \
    --output "${temporary_root}/version.json"
/usr/bin/python3 - "${temporary_root}/config.json" "${temporary_root}/version.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)
with open(sys.argv[2], encoding="utf-8") as handle:
    version = json.load(handle)
if config.get("max_queued_jobs") != 2:
    raise SystemExit("unexpected production queue limit")
if config.get("max_total_bases", 0) > 2_000_000:
    raise SystemExit("production input limit exceeds the reviewed VM policy")
if version.get("casandra_role") != "authoritative_cas_caller":
    raise SystemExit("CasAndra role contract mismatch")
if version.get("crispridentify_role") != "independent_array_overlay":
    raise SystemExit("CRISPRidentify role contract mismatch")
PY

echo "CasAndra Web deployment verification passed."

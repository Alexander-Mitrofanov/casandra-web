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
    [[ -n $(/usr/bin/find "${package_parent}/casandra_web" \
        -type f -name '*.py' -print -quit) ]] || return 1
    (
        cd "${package_parent}"
        /usr/bin/find casandra_web -type f -name '*.py' -print0 \
            | LC_ALL=C /usr/bin/sort -z \
            | /usr/bin/xargs -0 -r /usr/bin/sha256sum --zero
    )
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
grep -Fxq 'CASANDRA_WEB_MAX_RETAINED_INPUT_BASES=250000000' /etc/casandra-web.env \
    || fail "retained-input policy is not the reviewed value"
grep -Fxq 'CASANDRA_WEB_MIN_FREE_BYTES=20000000000' /etc/casandra-web.env \
    || fail "free-space admission floor is not the reviewed value"
grep -Fxq 'CASANDRA_WEB_MAX_JOB_STORAGE_BYTES=2000000000' /etc/casandra-web.env \
    || fail "per-job storage policy is not the reviewed value"
grep -Fxq 'CASANDRA_WEB_WORKER_CPU=3' /etc/casandra-web.env \
    || fail "scientific worker CPU policy is not the reviewed value"

current_link=/srv/casandra/releases/backend/current
[[ -L ${current_link} ]] || fail "backend current release link is missing"
release_root=$(readlink -e -- "${current_link}")
[[ ${release_root} =~ ^/srv/casandra/releases/backend/[0-9a-f]{24}$ \
    && -d ${release_root} && ! -L ${release_root} ]] \
    || fail "backend current link does not resolve to a content-addressed release"
release_directory_id=${release_root##*/}
release_environment=${release_root}/release.env
[[ -f ${release_environment} && ! -L ${release_environment} ]] \
    || fail "release identity environment is unavailable"
[[ $(stat -c '%U:%G:%a' "${release_environment}") == root:root:644 ]] \
    || fail "release identity environment ownership or mode is incorrect"
[[ $(/usr/bin/wc -l < "${release_environment}") -eq 1 ]] \
    || fail "release identity environment must contain exactly one line"
release_line=$(<"${release_environment}")
[[ ${release_line} =~ ^CASANDRA_WEB_RELEASE_ID=([0-9a-f]{64})$ ]] \
    || fail "release identity environment is malformed"
web_release_id=${BASH_REMATCH[1]}
[[ ${web_release_id:0:24} == "${release_directory_id}" ]] \
    || fail "public web release ID is not bound to the current release directory"
[[ -f ${release_root}/source/pyproject.toml \
    && ! -L ${release_root}/source/pyproject.toml ]] \
    || fail "release source metadata is unavailable"
[[ -x ${release_root}/venv/bin/python ]] \
    || fail "backend release Python interpreter is unavailable"
[[ -z $(/usr/bin/find "${release_root}/source/src/casandra_web" \
    -type l -print -quit) ]] || fail "release Python source contains a symbolic link"
[[ -z $(/usr/bin/find "${release_root}/source/src/casandra_web" \
    -type f ! -name '*.py' -print -quit) ]] \
    || fail "release Python package contains a non-source payload"
[[ $(backend_release_digest "${release_root}/source") == "${web_release_id}" ]] \
    || fail "release source digest does not match its public web release ID"
site_packages=$(
    "${release_root}/venv/bin/python" -I -B -c \
        'import sysconfig; print(sysconfig.get_path("purelib"))'
)
site_packages=$(readlink -e -- "${site_packages}")
[[ ${site_packages} == "${release_root}/venv/"* \
    && -d ${site_packages}/casandra_web \
    && ! -L ${site_packages}/casandra_web ]] \
    || fail "installed casandra_web package is outside the current release"
[[ -z $(/usr/bin/find "${site_packages}/casandra_web" -type l -print -quit) ]] \
    || fail "installed casandra_web Python source contains a symbolic link"
[[ -n $(/usr/bin/find "${site_packages}/casandra_web" \
    -type f -name '*.py' -print -quit) ]] \
    || fail "installed casandra_web Python source is empty"
[[ -z $(/usr/bin/find "${site_packages}/casandra_web" \
    -type f ! -name '*.py' -print -quit) ]] \
    || fail "installed casandra_web package contains an unattested payload"
/usr/bin/cmp -s \
    <(python_source_manifest "${release_root}/source/src") \
    <(python_source_manifest "${site_packages}") \
    || fail "installed casandra_web Python sources differ from release source"
module_file=$(
    "${release_root}/venv/bin/python" -I -B -c \
        'import casandra_web; print(casandra_web.__file__)'
)
[[ $(readlink -e -- "${module_file}") \
    == "${site_packages}/casandra_web/__init__.py" ]] \
    || fail "casandra_web imports do not resolve to the attested package"
"${release_root}/venv/bin/python" -I -B -m pip --isolated check >/dev/null \
    || fail "backend Python dependency check failed"

[[ $(stat -c '%U:%G:%a' /srv/casandra/jobs) == casandrasvc:casandrasvc:700 ]] \
    || fail "job root ownership or mode is incorrect"

for command in \
    /srv/casandra/releases/backend/current/venv/bin/casandra-web-api \
    /srv/casandra/releases/backend/current/venv/bin/casandra-web-worker \
    /srv/casandra/releases/backend/current/venv/bin/casandra-web-cleanup \
    /srv/casandra/releases/backend/current/venv/bin/casandra \
    /opt/crispr-workers/integration/bin/crispr-tools \
    /usr/local/libexec/crispr-web/run-crispridentify; do
    [[ -x ${command} ]] || fail "required executable is unavailable: ${command}"
done
[[ $(/srv/casandra/releases/backend/current/venv/bin/casandra --version) \
    == 'casandra 0.3.0.dev0' ]] \
    || fail "CasAndra version is not the reviewed release"
[[ $(/opt/crispr-workers/integration/bin/crispr-tools --version) \
    == 'crispr-tools 0.2.6' ]] \
    || fail "Integration version is not the reviewed release"
crispridentify_version_file=/opt/crispr-suite/CRISPRidentify/VERSION
[[ -f ${crispridentify_version_file} && ! -L ${crispridentify_version_file} ]] \
    || fail "CRISPRidentify version attestation is unavailable"
[[ $(<"${crispridentify_version_file}") == '2.0.0' ]] \
    || fail "CRISPRidentify version is not the reviewed release"
/srv/casandra/releases/backend/current/venv/bin/casandra \
    classify-cassette --help >/dev/null \
    || fail "CasAndra does not expose ordered cassette classification"
/srv/casandra/releases/backend/current/venv/bin/casandra \
    annotate-proteins --help >/dev/null \
    || fail "CasAndra does not expose provenance-bearing protein annotation"
[[ $(sha256sum /usr/local/libexec/crispr-web/run-crispridentify | cut -d' ' -f1) \
    == c3750da26aa56a620365ec489e7aab2777d326b728a565d74335cf0c623a7ad4 ]] \
    || fail "CRISPRidentify wrapper differs from the reviewed release"
scientific_verifier=/opt/crispr-suite/deployment/scientific/verify-scientific-release.py
[[ $(sha256sum "${scientific_verifier}" | cut -d' ' -f1) \
    == fdfa7fa1c6c9ac54bf126220637028494497954411e51dd0a4fed2f96a703a8f ]] \
    || fail "scientific release verifier differs from the reviewed release"
scientific_id=178f45ddd4080e30774d9e92d913a35088e253c24116e7149d6859639278ff42
[[ $(/usr/bin/python3 -I -B -S "${scientific_verifier}" \
    --manifest /etc/crispr-tools/release-manifest.json \
    --expected-sha256 "${scientific_id}" --require-current --print-digest) \
    == "${scientific_id}" ]] || fail "scientific release integrity gate failed"

systemd-analyze verify \
    /etc/systemd/system/casandra-web-api.service \
    /etc/systemd/system/casandra-web-worker.service \
    /etc/systemd/system/casandra-web-cleanup.service \
    /etc/systemd/system/casandra-web-cleanup.timer >/dev/null

for unit in casandra-web-api.service casandra-web-worker.service casandra-web-cleanup.timer; do
    systemctl is-enabled --quiet "${unit}" || fail "${unit} is not enabled"
    systemctl is-active --quiet "${unit}" || fail "${unit} is not active"
done
for unit in casandra-web-api.service casandra-web-worker.service \
    casandra-web-cleanup.service; do
    grep -Fxq \
        'EnvironmentFile=/srv/casandra/releases/backend/current/release.env' \
        "/etc/systemd/system/${unit}" \
        || fail "${unit} does not load the release-specific public identity"
done
[[ $(systemctl show casandra-web-api.service --property=MemoryMax --value) == 1610612736 ]] \
    || fail "API memory limit is not the reviewed value"
[[ $(systemctl show casandra-web-worker.service --property=MemoryMax --value) == 5368709120 ]] \
    || fail "worker memory limit is not the reviewed value"
[[ $(systemctl show casandra-web-worker.service --property=CPUQuotaPerSecUSec --value) == 3s ]] \
    || fail "worker CPU quota is not the reviewed value"

listener=$(ss -H -ltn 'sport = :8010')
[[ -n ${listener} ]] || fail "nothing is listening on port 8010"
if grep -Evq '127\.0\.0\.1:8010[[:space:]]' <<<"${listener}"; then
    fail "port 8010 has a non-loopback listener"
fi

nginx -t >/dev/null
nginx -T 2>&1 | grep -F 'client_max_body_size 110032768;' >/dev/null \
    || fail "Nginx request limit is not the reviewed value"
nginx -T 2>&1 | grep -F 'listen 127.0.0.1:8082 proxy_protocol default_server;' >/dev/null \
    || fail "Nginx is not using the reviewed loopback PROXY-v2 edge"
edge_listener=$(ss -H -ltn 'sport = :8082')
[[ -n ${edge_listener} && -z $(grep -Ev '127\.0\.0\.1:8082[[:space:]]' <<<"${edge_listener}") ]] \
    || fail "Nginx edge is not bound only to loopback port 8082"
if curl --fail --silent --show-error --max-time 4 \
    http://127.0.0.1:8082/casandra/api/v1/health >/dev/null 2>&1; then
    fail "Nginx edge accepted a request without PROXY protocol metadata"
fi

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
/usr/bin/python3 - "${temporary_root}/config.json" "${temporary_root}/version.json" \
    "${web_release_id}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)
with open(sys.argv[2], encoding="utf-8") as handle:
    version = json.load(handle)
expected_web_release_id = sys.argv[3]
if config.get("max_queued_jobs") != 1:
    raise SystemExit("unexpected production queue limit")
expected_limits = {
    "max_request_bytes": 110_000_000,
    "max_total_bases": 100_000_000,
    "max_record_bases": 100_000_000,
    "max_records": 10_000,
    "max_cas_only_request_bytes": 110_000_000,
    "max_cas_only_total_bases": 100_000_000,
    "max_cas_only_record_bases": 100_000_000,
    "max_cas_only_records": 10_000,
    "max_array_request_bytes": 4_500_000,
    "max_array_total_bases": 2_000_000,
    "max_array_record_bases": 2_000_000,
    "max_array_records": 20,
    "max_protein_request_bytes": 4_500_000,
    "max_protein_records": 10_000,
    "max_active_jobs": 2,
    "max_active_jobs_per_client": 1,
    "max_retained_jobs": 20,
    "max_job_lifetime_seconds": 28_800,
}
for name, expected in expected_limits.items():
    if config.get(name) != expected:
        raise SystemExit(f"unexpected production policy: {name}")
expected_policies = {
    "cas_only": {
        "when": {"include_crispr_arrays": False},
        "max_request_bytes": 110_000_000,
        "max_total_bases": 100_000_000,
        "max_record_bases": 100_000_000,
        "max_records": 10_000,
    },
    "with_crispr_arrays": {
        "when": {"include_crispr_arrays": True},
        "max_request_bytes": 4_500_000,
        "max_total_bases": 2_000_000,
        "max_record_bases": 2_000_000,
        "max_records": 20,
    },
}
if config.get("input_policies") != expected_policies:
    raise SystemExit("conditional nucleotide input policy mismatch")
expected_modes = {
    "complete_genome",
    "annotate_cas_genes",
    "classify_cassette",
    "metagenomic",
}
if set(config.get("analysis_modes", [])) != expected_modes:
    raise SystemExit("analysis-mode contract mismatch")
if version.get("casandra_role") != "authoritative_cas_caller":
    raise SystemExit("CasAndra role contract mismatch")
if version.get("crispridentify_role") != "independent_array_overlay":
    raise SystemExit("CRISPRidentify role contract mismatch")
if version.get("web_release_id") != expected_web_release_id:
    raise SystemExit("public web release identity does not match the current release")
expected_identity = {
    "casandra_bundle_id": "casandra-cas-only-cpu-bundle-v5-type-ii-architecture",
    "casandra_bundle_manifest_sha256": (
        "89657480e1135aec57f7e2b4a45fe5150f10fbdcbf80bf640e4325f7b921a071"
    ),
    "casandra_program_version": "0.3.0.dev0",
    "casandra_schema_version": 5,
    "casandra_bundle_role": "deployment_refit",
}
for name, expected in expected_identity.items():
    if version.get(name) != expected:
        raise SystemExit(f"CasAndra public identity mismatch: {name}")
if version.get("casandra_model") != {
    "bundle_id": expected_identity["casandra_bundle_id"],
    "bundle_manifest_sha256": expected_identity["casandra_bundle_manifest_sha256"],
    "program_version": expected_identity["casandra_program_version"],
    "schema_version": expected_identity["casandra_schema_version"],
    "bundle_role": expected_identity["casandra_bundle_role"],
}:
    raise SystemExit("nested CasAndra public identity mismatch")
PY

echo "CasAndra Web deployment verification passed."

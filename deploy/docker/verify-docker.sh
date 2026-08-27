#!/usr/bin/env bash
set -euo pipefail

compose_file=${CASANDRA_COMPOSE_FILE:-/srv/casandra/compose.yml}
[[ -f ${compose_file} ]] || {
    echo "compose file is unavailable: ${compose_file}" >&2
    exit 66
}

fail() {
    echo "verification failed: $*" >&2
    exit 1
}

temporary_root=$(mktemp -d /tmp/casandra-web-docker-verify.XXXXXX)
trap 'rm -rf -- "${temporary_root}"' EXIT

for container in casandra-edge casandra-api casandra-worker casandra-cleanup fasta-web; do
    [[ $(docker inspect --format '{{.State.Running}}' "${container}" 2>/dev/null) == true ]] \
        || fail "container is not running: ${container}"
done

api_network=$(docker inspect --format '{{.HostConfig.NetworkMode}}' casandra-api)
[[ ${api_network} == casandra-ingress ]] || fail "API is not attached only to casandra-ingress"
api_ports=$(docker inspect --format '{{json .HostConfig.PortBindings}}' casandra-api)
[[ ${api_ports} == null || ${api_ports} == '{}' ]] || fail "API has a host port binding"
api_address=$(docker inspect --format '{{(index .NetworkSettings.Networks "casandra-ingress").IPAddress}}' casandra-api)
[[ ${api_address} == 172.30.249.3 ]] || fail "API does not have its reviewed ingress address"
edge_address=$(docker inspect --format '{{(index .NetworkSettings.Networks "casandra-ingress").IPAddress}}' casandra-edge)
[[ ${edge_address} == 172.30.249.2 ]] || fail "edge does not have its reviewed ingress address"
edge_host_address=$(docker inspect --format '{{(index .NetworkSettings.Networks "casandra-edge-host").IPAddress}}' casandra-edge)
[[ ${edge_host_address} == 172.30.250.2 ]] || fail "edge does not have its reviewed host-edge address"
edge_binding=$(docker port casandra-edge 8080/tcp)
[[ ${edge_binding} == 127.0.0.1:8082 ]] || fail "edge is not bound only to loopback port 8082"
worker_network=$(docker inspect --format '{{.HostConfig.NetworkMode}}' casandra-worker)
[[ ${worker_network} == none ]] || fail "worker network is not disabled"
cleanup_network=$(docker inspect --format '{{.HostConfig.NetworkMode}}' casandra-cleanup)
[[ ${cleanup_network} == none ]] || fail "cleanup network is not disabled"
for container in casandra-worker casandra-cleanup; do
    [[ $(docker inspect --format '{{json .Config.Healthcheck.Test}}' "${container}") == '["NONE"]' ]] \
        || fail "${container} did not disable the inherited HTTP healthcheck"
done

scientific_image_id=$(docker inspect --format '{{.Image}}' casandra-api)
for container in casandra-worker casandra-cleanup; do
    [[ $(docker inspect --format '{{.Image}}' "${container}") == "${scientific_image_id}" ]] \
        || fail "${container} is not running the same reviewed image as the API"
done

verify_limits() {
    local container=$1 expected_memory=$2 expected_reservation=$3 expected_cpu=$4 expected_pids=$5
    [[ $(docker inspect --format '{{.HostConfig.Memory}}' "${container}") == "${expected_memory}" ]] \
        || fail "${container} memory limit differs from the reviewed value"
    [[ $(docker inspect --format '{{.HostConfig.MemoryReservation}}' "${container}") == "${expected_reservation}" ]] \
        || fail "${container} memory reservation differs from the reviewed value"
    [[ $(docker inspect --format '{{.HostConfig.NanoCpus}}' "${container}") == "${expected_cpu}" ]] \
        || fail "${container} CPU limit differs from the reviewed value"
    [[ $(docker inspect --format '{{.HostConfig.PidsLimit}}' "${container}") == "${expected_pids}" ]] \
        || fail "${container} PID limit differs from the reviewed value"
}
verify_limits casandra-edge 67108864 0 50000000 64
verify_limits casandra-api 201326592 134217728 150000000 96
verify_limits casandra-worker 996147200 671088640 750000000 192
verify_limits casandra-cleanup 67108864 0 50000000 32

for container in casandra-edge casandra-api casandra-worker casandra-cleanup; do
    user=$(docker inspect --format '{{.Config.User}}' "${container}")
    [[ ${user} == 10001:10001 ]] || fail "${container} is not using the service UID"
    privileged=$(docker inspect --format '{{.HostConfig.Privileged}}' "${container}")
    [[ ${privileged} == false ]] || fail "${container} is privileged"
    readonly=$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "${container}")
    [[ ${readonly} == true ]] || fail "${container} root filesystem is writable"
done

edge_readonly=$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' casandra-edge)
[[ ${edge_readonly} == true ]] || fail "casandra-edge root filesystem is writable"
docker exec casandra-edge caddy validate --config /etc/caddy/Caddyfile >/dev/null
docker exec casandra-edge grep -Fq 'handle /casandra/api/*' /etc/caddy/Caddyfile \
    || fail "dedicated edge does not contain the CasAndra API route"
docker exec casandra-edge grep -Fq 'proxy_protocol' /etc/caddy/Caddyfile \
    || fail "dedicated edge does not require the reviewed PROXY protocol path"
docker exec casandra-edge grep -Fq 'fallback_policy require' /etc/caddy/Caddyfile \
    || fail "dedicated edge does not reject connections without PROXY metadata"

if curl --silent --show-error --max-time 4 \
    http://127.0.0.1:8082/casandra/api/v1/health >/dev/null 2>&1; then
    fail "dedicated edge accepted a direct request without PROXY metadata"
fi

healthy=false
for _attempt in 1 2 3 4 5 6 7 8 9 10; do
    if /usr/bin/python3 - "${temporary_root}/health.json" <<'PY'
import ipaddress
import socket
import struct
import sys

signature = b"\r\n\r\n\x00\r\nQUIT\n"
source = ipaddress.ip_address("203.0.113.10").packed
destination = ipaddress.ip_address("127.0.0.1").packed
header = struct.pack("!12sBBH4s4sHH", signature, 0x21, 0x11, 12, source, destination, 49152, 443)
request = b"GET /casandra/api/v1/health HTTP/1.1\r\nHost: health.invalid\r\nConnection: close\r\n\r\n"
with socket.create_connection(("127.0.0.1", 8082), timeout=5) as connection:
    connection.sendall(header + request)
    response = b""
    while block := connection.recv(65536):
        response += block
status, _, body = response.partition(b"\r\n\r\n")
if b" 200 " not in status.split(b"\r\n", 1)[0]:
    raise SystemExit(1)
with open(sys.argv[1], "wb") as handle:
    handle.write(body)
PY
    then
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
[[ ${healthy} == true ]] || fail "Caddy/API/worker health did not become ready"

scientific_image=$(docker inspect --format '{{.Config.Image}}' casandra-worker)
docker run --rm --network none "${scientific_image}" \
    /usr/bin/test -r /opt/casandra-web/config/runners.json \
    || fail "scientific service user cannot read its runner configuration"
docker run --rm --network none "${scientific_image}" \
    /opt/integration/venv/bin/python -c \
    'from crispr_integration.runner import load_runner_config; c=load_runner_config("/opt/casandra-web/config/runners.json"); assert c.crispridentify == ("/opt/casandra-web/bin/run-crispridentify",); assert c.spacerplacer == ("/usr/bin/false",); assert c.crispr_evor == ("/usr/bin/false",)' \
    || fail "Integration cannot load the reviewed identify-only runner configuration"
docker run --rm --network none "${scientific_image}" \
    /opt/casandra-web/bin/run-crispridentify --help >/dev/null \
    || fail "CRISPRidentify wrapper cannot import the bundled source tree"
docker run --rm --network none "${scientific_image}" \
    /usr/local/bin/python -c \
    'import ctypes; ctypes.CDLL("/opt/crispridentify/components/native/libliteral_fuzzy.so")' \
    || fail "scientific service user cannot load CRISPRidentify's native matcher"
[[ $(docker run --rm --network none "${scientific_image}" \
    /opt/casandra/venv/bin/casandra --version) == 'casandra 0.2.0.dev0' ]] \
    || fail "CasAndra version is not the reviewed release"
[[ $(docker run --rm --network none "${scientific_image}" \
    /opt/integration/venv/bin/crispr-tools --version) == 'crispr-tools 0.2.6' ]] \
    || fail "Integration version is not the reviewed release"
docker run --rm --network none "${scientific_image}" \
    /opt/casandra/venv/bin/casandra inspect-model > "${temporary_root}/model.json"
/usr/bin/python3 - "${temporary_root}/model.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle)
if (
    value.get("integrity") != "verified"
    or value.get("cpu_only") is not True
    or value.get("offline_inference") is not True
    or not value.get("bundle_id")
):
    raise SystemExit(1)
PY
[[ $(docker run --rm --network none --entrypoint /bin/sh "${scientific_image}" \
    -c 'cat /opt/crispridentify/VERSION') == '2.0.0' ]] \
    || fail "CRISPRidentify version is not the reviewed release"

docker compose -f "${compose_file}" config --quiet
echo "Docker/Caddy CasAndra Web deployment verification passed."

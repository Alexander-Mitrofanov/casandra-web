#!/usr/bin/env bash
set -euo pipefail

script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
base_image=${CASANDRA_CADDY_BASE_IMAGE:-fasta-web:denbi}
image_tag=${CASANDRA_EDGE_IMAGE:-${CASANDRA_CADDY_IMAGE:-casandra-edge:local}}

docker image inspect "${base_image}" >/dev/null 2>&1 || {
    echo "required local Caddy base image is unavailable: ${base_image}" >&2
    exit 69
}
docker build --pull=false --build-arg "BASE_IMAGE=${base_image}" \
    --tag "${image_tag}" "${script_root}"
docker run --rm --entrypoint caddy "${image_tag}" \
    validate --config /etc/caddy/Caddyfile
echo "Built and validated ${image_tag}. No running container was changed."

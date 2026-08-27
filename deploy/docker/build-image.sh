#!/usr/bin/env bash
set -euo pipefail

umask 077
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_root=$(readlink -f -- "${script_root}/../../..")
integration_root=${CASANDRA_INTEGRATION_ROOT:-${project_root}/../WebServer-Identify-SpacerPlacer-evOr/Integration}
image_tag=${CASANDRA_WEB_IMAGE:-casandra-web:local}
base_image=${CASANDRA_IDENTIFY_BASE_IMAGE:-crispridentify-v2-backend:bb3e31d}
build_network=${CASANDRA_DOCKER_BUILD_NETWORK:-default}

case ${build_network} in
    default|host|none) ;;
    *)
        echo "CASANDRA_DOCKER_BUILD_NETWORK must be default, host, or none" >&2
        exit 64
        ;;
esac

[[ -f ${project_root}/tool/pyproject.toml ]] || {
    echo "CasAndra tool source is unavailable beneath ${project_root}" >&2
    exit 66
}
[[ -f ${project_root}/WebServer/backend/pyproject.toml ]] || {
    echo "WebServer backend source is unavailable beneath ${project_root}" >&2
    exit 66
}
[[ -f ${integration_root}/pyproject.toml ]] || {
    echo "Integration source is unavailable: ${integration_root}" >&2
    exit 66
}
docker image inspect "${base_image}" >/dev/null 2>&1 || {
    echo "required local base image is unavailable: ${base_image}" >&2
    exit 69
}

context_root=$(mktemp -d /tmp/casandra-web-image.XXXXXX)
trap 'rm -rf -- "${context_root}"' EXIT

copy_source() {
    source_dir=$1
    target_dir=$2
    mkdir -p -- "${target_dir}"
    tar -C "${source_dir}" \
        --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
        --exclude='.pytest_cache' --exclude='.ruff_cache' --exclude='*.pyc' \
        --exclude='*.pyo' --exclude='*.egg-info' --exclude='build' --exclude='dist' \
        -cf - . | tar -C "${target_dir}" -xf -
}

copy_source "${project_root}/WebServer/backend" "${context_root}/backend"
copy_source "${project_root}/tool" "${context_root}/casandra-tool"
copy_source "${integration_root}" "${context_root}/integration"
patch --batch --forward -d "${context_root}/integration" -p1 \
    < "${script_root}/integration-signal-cleanup.patch"
cp -- "${script_root}/Dockerfile" "${script_root}/run-crispridentify" \
    "${script_root}/cleanup-loop" "${script_root}/runners.json" "${context_root}/"

docker build --pull=false \
    --network "${build_network}" \
    --build-arg "BASE_IMAGE=${base_image}" \
    --label "org.opencontainers.image.base.digest=$(docker image inspect --format '{{.Id}}' "${base_image}")" \
    --tag "${image_tag}" \
    "${context_root}"

echo "Built ${image_tag} from local base ${base_image}."

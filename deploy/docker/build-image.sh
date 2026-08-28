#!/usr/bin/env bash
set -euo pipefail

umask 077
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_root=$(readlink -f -- "${script_root}/../../..")
tool_overlay_root=${script_root}/casandra-tool-overlay
tool_release_lock=${script_root}/casandra-tool-release.sha256
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
[[ -f ${tool_release_lock} ]] || {
    echo "Pinned CasAndra tool release manifest is unavailable" >&2
    exit 66
}
for overlay_file in \
    pyproject.toml \
    src/casandra/__init__.py \
    src/casandra/api.py \
    src/casandra/cassette_input.py \
    src/casandra/cli.py \
    src/casandra/pipeline.py \
    src/casandra/prediction.py \
    src/casandra/protein_annotation.py; do
    [[ -f ${tool_overlay_root}/${overlay_file} ]] || {
        echo "Tracked CasAndra tool overlay is incomplete: ${overlay_file}" >&2
        exit 66
    }
done
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
copy_source "${tool_overlay_root}" "${context_root}/casandra-tool"
copy_source "${integration_root}" "${context_root}/integration"
patch --batch --forward -d "${context_root}/integration" -p1 \
    < "${script_root}/integration-signal-cleanup.patch"
cp -- "${script_root}/Dockerfile" "${script_root}/run-crispridentify" \
    "${script_root}/cleanup-loop" "${script_root}/runners.json" "${context_root}/"

generated_tool_release=${context_root}/casandra-tool-release.generated.sha256
(
    cd "${context_root}/casandra-tool"
    {
        printf '%s\0' LICENSE README.md pyproject.toml
        find src/casandra -type f \
            ! -path '*/__pycache__/*' ! -name '*.pyc' ! -name '*.pyo' -print0
    } | LC_ALL=C sort -z | xargs -0 sha256sum
) > "${generated_tool_release}"
cmp --silent "${tool_release_lock}" "${generated_tool_release}" || {
    echo "Post-overlay CasAndra source/model tree differs from the pinned release manifest" >&2
    diff --unified "${tool_release_lock}" "${generated_tool_release}" >&2 || true
    exit 65
}
tool_release_digest=$(sha256sum "${tool_release_lock}" | awk '{print $1}')
model_bundle_manifest_digest=$(awk \
    '$2 == "src/casandra/models/manifest.json" {print $1}' \
    "${tool_release_lock}")
[[ ${tool_release_digest} =~ ^[0-9a-f]{64}$ \
    && ${model_bundle_manifest_digest} =~ ^[0-9a-f]{64}$ ]] || {
    echo "Pinned CasAndra release manifest is malformed" >&2
    exit 65
}
[[ $(sha256sum "${context_root}/casandra-tool/src/casandra/models/manifest.json" \
    | awk '{print $1}') == "${model_bundle_manifest_digest}" ]] || {
    echo "CasAndra model-bundle manifest differs from the pinned release" >&2
    exit 65
}

tool_overlay_digest=$(
    tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' \
        -C "${tool_overlay_root}" -cf - pyproject.toml src \
        | sha256sum | awk '{print $1}'
)
[[ ${tool_overlay_digest} =~ ^[0-9a-f]{64}$ ]] || {
    echo "Could not calculate the tracked CasAndra tool overlay digest" >&2
    exit 70
}

docker build --pull=false \
    --network "${build_network}" \
    --build-arg "BASE_IMAGE=${base_image}" \
    --label "org.opencontainers.image.base.digest=$(docker image inspect --format '{{.Id}}' "${base_image}")" \
    --label "org.casandra.tool.overlay.digest=sha256:${tool_overlay_digest}" \
    --label "org.casandra.tool.release-manifest.digest=sha256:${tool_release_digest}" \
    --label "org.casandra.model.bundle-manifest.digest=sha256:${model_bundle_manifest_digest}" \
    --label "org.casandra.tool.version=0.3.0.dev0" \
    --tag "${image_tag}" \
    "${context_root}"

echo "Built ${image_tag} from local base ${base_image}."

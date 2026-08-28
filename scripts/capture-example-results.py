#!/usr/bin/env python3
"""Capture real completed CasAndra jobs as same-origin frontend examples."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

MODE_INPUTS = {
    "complete_genome": ("input.fna", False),
    "annotate_cas_genes": ("input.faa", False),
    "classify_cassette": ("input.faa", False),
    "metagenomic": ("input.fna", False),
}


def replace_example_directory(staged: Path, destination: Path) -> None:
    """Replace one captured example without merging with stale artifacts."""

    if destination.is_symlink():
        raise RuntimeError(f"Refusing to replace symlinked example directory: {destination}")
    backup = destination.with_name(f".{destination.name}.capture-backup")
    if backup.exists() or backup.is_symlink():
        raise RuntimeError(f"A previous capture backup still exists: {backup}")
    if not destination.exists():
        staged.replace(destination)
        return

    destination.replace(backup)
    try:
        staged.replace(destination)
    except BaseException:
        backup.replace(destination)
        raise
    shutil.rmtree(backup)


def request_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    origin: str,
    body: dict | None = None,
) -> dict:
    headers = {"Accept": "application/json", "Origin": origin}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code} from {url}: {detail}") from error


def download(url: str, *, token: str, origin: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "Authorization": f"Bearer {token}",
            "Origin": origin,
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def capture_mode(
    mode: str,
    *,
    api_base: str,
    site_origin: str,
    input_root: Path,
    output_root: Path,
    poll_seconds: float,
) -> None:
    filename, include_arrays = MODE_INPUTS[mode]
    input_path = input_root / mode / filename
    sequence = input_path.read_text(encoding="ascii")
    created = request_json(
        f"{api_base}/jobs",
        method="POST",
        origin=site_origin,
        body={
            "sequence": sequence,
            "filename": filename,
            "analysis_mode": mode,
            "include_crispr_arrays": include_arrays,
        },
    )
    job = created.get("job", created)
    job_id = str(job["job_id"])
    token = str(created["access_token"])
    print(f"{mode}: submitted {job_id}", flush=True)

    previous = None
    while True:
        job = request_json(f"{api_base}/jobs/{job_id}", token=token, origin=site_origin)
        state = (job.get("status"), job.get("phase"))
        if state != previous:
            print(f"{mode}: {state[0]} / {state[1]}", flush=True)
            previous = state
        if job.get("status") in {"completed", "failed", "cancelled"}:
            break
        time.sleep(poll_seconds)
    if job.get("status") != "completed":
        raise RuntimeError(f"{mode} did not complete: {job.get('error')}")

    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / mode
    with tempfile.TemporaryDirectory(prefix=f".{mode}.capture-", dir=output_root) as temporary:
        staged = Path(temporary)
        shutil.copy2(input_path, staged / filename)
        artifact_root = staged / "artifacts"
        artifact_root.mkdir()
        bundled_artifacts = []
        interactive_results = None
        for artifact in job.get("artifacts", []):
            name = str(artifact.get("name") or "")
            if not name or PurePosixPath(name).name != name:
                raise RuntimeError(f"Unsafe artifact name from service: {name!r}")
            artifact_url = urllib.parse.urljoin(
                api_base + "/", str(artifact["download_url"])
            )
            content = download(artifact_url, token=token, origin=site_origin)
            artifact_root.joinpath(name).write_bytes(content)
            if name == "casandra-results.json":
                interactive_results = json.loads(content)
            bundled_artifacts.append(
                {key: value for key, value in artifact.items() if key != "download_url"}
                | {"bundled_path": f"examples/{mode}/artifacts/{name}"}
            )

        if interactive_results is None:
            raise RuntimeError(f"{mode} did not publish casandra-results.json")
        captured_job = {
            key: value
            for key, value in job.items()
            if key not in {"expires_at", "queue_position"}
        }
        captured_job["artifacts"] = bundled_artifacts
        captured_job["interactive_results"] = interactive_results
        staged.joinpath("job.json").write_text(
            json.dumps(captured_job, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        replace_example_directory(staged, destination)
    print(
        f"{mode}: captured {len(bundled_artifacts)} artifacts and "
        f"{len(interactive_results.get('features', []))} interactive features",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-origin", required=True)
    parser.add_argument("--site-origin", required=True)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--modes", nargs="+", choices=tuple(MODE_INPUTS), required=True)
    parser.add_argument("--poll-seconds", type=float, default=2.5)
    args = parser.parse_args()
    api_base = args.api_origin.rstrip("/") + "/casandra/api/v1"
    for mode in args.modes:
        capture_mode(
            mode,
            api_base=api_base,
            site_origin=args.site_origin,
            input_root=args.input_root,
            output_root=args.output_root,
            poll_seconds=args.poll_seconds,
        )


if __name__ == "__main__":
    main()

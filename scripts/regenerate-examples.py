#!/usr/bin/env python3
"""Regenerate all four examples through the local API, queue and real scientific CLI.

Requires the backend test dependencies (httpx2). No public service is contacted.
Inputs are unchanged, arrays are off, and every download is authenticated and hashed.
"""

from __future__ import annotations

# Import the repository backend only after its source path is selected below.
# ruff: noqa: E402

import argparse
import asyncio
import hashlib
import importlib.util
import json
import secrets
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB / "backend/src"))

import httpx2 as httpx
from casandra_web.api import create_app
from casandra_web.config import Settings
from casandra_web.model_registry import verify_bundle
from casandra_web.release_contract import (
    BUNDLE_ID,
    BUNDLE_MANIFEST_SHA256,
    PROGRAM_VERSION,
)
from casandra_web.worker import Worker

spec = importlib.util.spec_from_file_location(
    "capture_examples", WEB / "scripts/capture-example-results.py"
)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


async def regenerate(args, work: Path, staged: Path) -> dict:
    command = tuple(json.loads(args.casandra_command))
    bundle_id, role = verify_bundle(args.bundle.resolve(), BUNDLE_MANIFEST_SHA256)
    if bundle_id != BUNDLE_ID:
        raise RuntimeError("Unexpected release bundle")
    version = (
        await asyncio.to_thread(
            subprocess.check_output,
            [*command, "--version"],
            text=True,
        )
    ).strip()
    if version != f"casandra {PROGRAM_VERSION}":
        raise RuntimeError(f"Wrong scientific runtime: {version}")
    inspection = json.loads(
        await asyncio.to_thread(
            subprocess.check_output,
            [*command, "inspect-model", "--model", str(args.bundle.resolve())],
            text=True,
        )
    )
    if (
        inspection.get("bundle_id") != BUNDLE_ID
        or inspection.get("integrity") != "verified"
    ):
        raise RuntimeError("Scientific CLI failed bundle inspection")
    source_hashes = {
        str(path.relative_to(WEB)): sha(path.read_bytes())
        for path in sorted((WEB / "backend/src/casandra_web").glob("*.py"))
    }
    release_id = sha(json.dumps(source_hashes, sort_keys=True).encode())
    origin = "http://127.0.0.1:4173"
    settings = replace(
        Settings.from_env(),
        data_root=work / "jobs",
        database_path=work / "jobs/queue.sqlite3",
        token_pepper=secrets.token_hex(32),
        cors_origins=(origin,),
        casandra_command=command,
        identify_command=("/usr/bin/false",),
        identify_runner_config=None,
        model_name=BUNDLE_ID,
        casandra_model_dir=args.bundle.resolve(),
        casandra_bundle_id=BUNDLE_ID,
        casandra_bundle_manifest_sha256=BUNDLE_MANIFEST_SHA256,
        casandra_program_version=PROGRAM_VERSION,
        casandra_schema_version=5,
        casandra_bundle_role=role,
        web_release_id=release_id,
        preflight_scientific_runtime=False,
        worker_cpu=args.threads,
        stage_timeout_seconds=1800,
        max_request_bytes=4_500_000,
        max_total_bases=2_000_000,
        max_record_bases=2_000_000,
        max_retained_input_bases=20_000_000,
        max_submissions_per_window=20,
        min_free_bytes=500_000_000,
        min_free_inodes=1000,
    )
    app = create_app(settings)
    worker = Worker(settings, store=app.state.store)
    worker.validate_runtime()
    receipt = {
        "schema_version": 1,
        "captured_on": datetime.now(timezone.utc).date().isoformat(),
        "capture_method": "local ASGI HTTP API, SQLite queue, real CLI worker, authenticated downloads",
        "api_origin": "local-asgi://casandra",
        "bundle_id": BUNDLE_ID,
        "bundle_manifest_sha256": BUNDLE_MANIFEST_SHA256,
        "runtime_version": PROGRAM_VERSION,
        "web_release_id": release_id,
        "backend_source_sha256": source_hashes,
        "inputs_unchanged": True,
        "all_artifact_hashes_verified": True,
        "array_detection_tested": False,
        "modes": [],
    }
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Origin": origin},
        ) as client,
    ):
        public_version = (await client.get("/casandra/api/v1/version")).json()
        assert public_version["casandra_bundle_id"] == BUNDLE_ID
        assert public_version["api_version"] == "1.2.0"
        for mode, (filename, arrays) in capture.MODE_INPUTS.items():
            mode_dir = staged / mode
            mode_dir.mkdir()
            source = args.input_root / mode / filename
            shutil.copy2(source, mode_dir / filename)
            response = await client.post(
                "/casandra/api/v1/jobs",
                json={
                    "sequence": source.read_text(),
                    "filename": filename,
                    "analysis_mode": mode,
                    "include_crispr_arrays": arrays,
                },
            )
            assert response.status_code == 202, response.text
            created = response.json()
            job_id = created["job"]["job_id"]
            token = created["access_token"]
            auth = {"Authorization": f"Bearer {token}"}
            print(f"{mode}: running real worker for {job_id}", flush=True)
            assert await asyncio.to_thread(worker.run_once)
            print(f"{mode}: worker completed; reading API result", flush=True)
            response = await client.get(f"/casandra/api/v1/jobs/{job_id}", headers=auth)
            assert response.status_code == 200, response.text
            job = response.json()
            assert job["status"] == "completed", job.get("error")
            provenance = job["summary"]["provenance"]
            assert provenance["casandra_manifest_sha256"] == BUNDLE_MANIFEST_SHA256
            assert provenance["casandra_program_version"] == PROGRAM_VERSION
            artifact_root = mode_dir / "artifacts"
            artifact_root.mkdir()
            artifacts = []
            for artifact in job["artifacts"]:
                name = artifact["name"]
                assert Path(name).name == name
                url = artifact["download_url"]
                assert url.startswith(f"/casandra/api/v1/jobs/{job_id}/artifacts/")
                assert (await client.get(url)).status_code == 401
                response = await client.get(url, headers=auth)
                assert response.status_code == 200, response.text
                content = response.content
                assert len(content) == artifact["size_bytes"]
                assert sha(content) == artifact["sha256"]
                (artifact_root / name).write_bytes(content)
                artifacts.append(
                    {k: v for k, v in artifact.items() if k != "download_url"}
                    | {
                        "bundled_path": f"examples/{mode}/artifacts/{name}",
                    }
                )
            complete = json.loads((artifact_root / "casandra-results.json").read_text())
            assert complete["summary"] == job["summary"]
            assert (
                complete["release_identity"]["bundle_manifest_sha256"]
                == BUNDLE_MANIFEST_SHA256
            )
            with zipfile.ZipFile(artifact_root / "casandra-results.zip") as archive:
                assert archive.testzip() is None
                assert (
                    archive.read("exports/casandra-results.json")
                    == (artifact_root / "casandra-results.json").read_bytes()
                )
                manifest = json.loads(archive.read("casandra/manifest.json"))
                for name, record in manifest["files"].items():
                    content = archive.read("casandra/" + name)
                    assert (
                        len(content) == record["size"]
                        and sha(content) == record["sha256"]
                    )
            public_job = {
                k: v
                for k, v in job.items()
                if k not in {"expires_at", "queue_position"}
            }
            public_job.update(artifacts=artifacts, interactive_results=complete)
            serialized = json.dumps(public_job)
            assert token not in serialized and "download_url" not in serialized
            save(mode_dir / "job.json", public_job)
            receipt["modes"].append(
                {
                    "mode": mode,
                    "job_id": job_id,
                    "input_sha256": sha(source.read_bytes()),
                    "artifact_count": len(artifacts),
                    "overview": job["summary"]["overview"],
                    "specificity_decisions": job["summary"]["specificity_decisions"],
                }
            )
            print(f"{mode}: verified {len(artifacts)} artifacts", flush=True)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument(
        "--casandra-command", required=True, help="JSON argument array for the real CLI"
    )
    parser.add_argument(
        "--input-root", type=Path, default=WEB / "frontend/public/examples"
    )
    parser.add_argument(
        "--output-root", type=Path, default=WEB / "frontend/public/examples"
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        required=True,
        help="New directory; private jobs retained for audit",
    )
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    args.output_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".examples-", dir=args.output_root.parent
    ) as temp:
        staged = Path(temp) / "examples"
        staged.mkdir()
        for path in args.input_root.glob("*.json"):
            if path.name != "capture-manifest.json":
                shutil.copy2(path, staged / path.name)
        receipt = asyncio.run(regenerate(args, args.work_dir, staged))
        save(staged / "capture-manifest.json", receipt)
        save(args.work_dir / "capture-receipt.json", receipt)
        capture.replace_example_directory(staged, args.output_root)
    print("All four examples replaced together after verification.", flush=True)


if __name__ == "__main__":
    main()

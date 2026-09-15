"""Exercise capture provenance and artifact checks without submitting public jobs."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/capture-example-results.py"
spec = importlib.util.spec_from_file_location("example_capture", SCRIPT)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    inputs = tmp_path / "inputs" / "annotate_cas_genes"
    inputs.mkdir(parents=True)
    (inputs / "input.faa").write_text(">test\nMKTWACDEFGHIKLMNPQRSTVWY\n")
    content = b'{"features":[]}'
    job = {
        "job_id": "job-123", "status": "completed", "expires_at": 123,
        "summary": {"provenance": {
            "casandra_bundle_id": "candidate", "casandra_manifest_sha256": "a" * 64,
        }},
        "artifacts": [{
            "name": "casandra-results.json", "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "download_url": "/casandra/api/v1/jobs/job-123/artifacts/result",
        }],
    }
    downloads = []
    monkeypatch.setattr(capture, "request_json", lambda *a, **kw: (
        {"job": job, "access_token": "private-token"} if kw.get("method") == "POST" else job
    ))

    def download(url, **kwargs):
        downloads.append(url)
        return content

    monkeypatch.setattr(capture, "download", download)
    kwargs = {
        "api_base": "https://server.example/casandra/api/v1",
        "site_origin": "https://site.example",
        "input_root": inputs.parent, "output_root": tmp_path / "output", "poll_seconds": 0,
        "expected_bundle_id": "candidate", "expected_manifest_sha256": "a" * 64,
    }
    return job, downloads, kwargs


def test_verified_capture_removes_live_credentials_and_links(scenario):
    _, downloads, kwargs = scenario
    capture.capture_mode("annotate_cas_genes", **kwargs)
    text = (kwargs["output_root"] / "annotate_cas_genes/job.json").read_text()
    assert len(downloads) == 1
    assert "private-token" not in text and "download_url" not in text
    assert "expires_at" not in text
    assert json.loads(text)["interactive_results"] == {"features": []}


@pytest.mark.parametrize("mutation", ["bundle", "checksum", "origin", "other_job"])
def test_bad_capture_preserves_existing_example(scenario, mutation):
    job, downloads, kwargs = scenario
    destination = kwargs["output_root"] / "annotate_cas_genes"
    destination.mkdir(parents=True)
    (destination / "job.json").write_text("previous example")
    artifact = job["artifacts"][0]
    if mutation == "bundle":
        job["summary"]["provenance"]["casandra_bundle_id"] = "old"
    elif mutation == "checksum":
        artifact["sha256"] = "b" * 64
    elif mutation == "origin":
        artifact["download_url"] = "https://unrelated.example/result"
    else:
        artifact["download_url"] = "/casandra/api/v1/jobs/other-job/artifacts/result"
    with pytest.raises(RuntimeError):
        capture.capture_mode("annotate_cas_genes", **kwargs)
    assert (destination / "job.json").read_text() == "previous example"
    if mutation != "checksum":
        assert not downloads

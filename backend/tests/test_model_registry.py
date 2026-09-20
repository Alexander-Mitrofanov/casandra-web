from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

import casandra_web.worker as worker_module
from casandra_web.config import Settings
from casandra_web.db import Store
from casandra_web.model_registry import load_model, register
from casandra_web.models import JobSubmission
from casandra_web.service import JobService
from casandra_web.worker import Worker, WorkerStopping


@pytest.fixture
def registry(tmp_path):
    bundle = tmp_path / "models" / "kira"
    bundle.mkdir(parents=True)
    files = {
        "config.json": json.dumps({"bundle_id": "kira-full-v1", "bundle_role": "deployment_refit"}),
        "protein/manifest.json": "{}",
        "cassette_architecture/manifest.json": "{}",
        "protein/profiles.hmm": "test-profile",
    }
    artifacts = {}
    for name, content in files.items():
        path = bundle / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(content)
        artifacts[name] = {"size": path.stat().st_size,
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (bundle / "manifest.json").write_text(json.dumps({
        "bundle_id": "kira-full-v1", "artifacts": artifacts,
    }))
    registry_path = tmp_path / "registry.json"
    entry = register(registry_path, "kira-full-v1", bundle, "0.3.0.dev2", 5)
    return registry_path, bundle, entry


def test_named_selection_pins_identity_and_default_restores_old_env(registry, monkeypatch):
    path, bundle, entry = registry
    monkeypatch.setenv("CASANDRA_WEB_MODEL_REGISTRY", str(path))
    monkeypatch.setenv("CASANDRA_WEB_MODEL_NAME", "kira-full-v1")
    # Legacy pins remain available for rollback; named selection derives its own pins.
    for suffix, value in {
        "BUNDLE_ID": "old", "BUNDLE_MANIFEST_SHA256": "a" * 64,
        "PROGRAM_VERSION": "0.3.0.dev2", "SCHEMA_VERSION": "5",
        "BUNDLE_ROLE": "deployment_refit",
    }.items():
        monkeypatch.setenv("CASANDRA_WEB_CASANDRA_" + suffix, value)
    selected = Settings.from_env()
    assert selected.casandra_model_dir == bundle
    assert selected.casandra_bundle_id == "kira-full-v1"
    assert selected.casandra_bundle_manifest_sha256 == entry["manifest_sha256"]
    monkeypatch.setenv("CASANDRA_WEB_MODEL_NAME", "default")
    restored = Settings.from_env()
    assert restored.casandra_model_dir is None
    assert restored.casandra_bundle_id == "old"


def test_unknown_name_and_missing_registry_fail_closed(monkeypatch, registry):
    path, _, _ = registry
    monkeypatch.setenv("CASANDRA_WEB_MODEL_NAME", "unknown")
    monkeypatch.delenv("CASANDRA_WEB_MODEL_REGISTRY", raising=False)
    with pytest.raises(ValueError, match="REGISTRY is required"):
        Settings.from_env()
    monkeypatch.setenv("CASANDRA_WEB_MODEL_REGISTRY", str(path))
    with pytest.raises(ValueError, match="not registered"):
        Settings.from_env()


@pytest.mark.parametrize("artifact", ["manifest.json", "protein/profiles.hmm"])
def test_registry_rejects_tampering(registry, tmp_path, artifact):
    path, bundle, _ = registry
    with (bundle / artifact).open("a") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="registry pin|integrity failed"):
        load_model(path, "kira-full-v1", data_root=tmp_path / "jobs")


def test_registration_is_immutable_idempotent_and_outside_job_data(registry, tmp_path):
    path, bundle, entry = registry
    assert register(path, "kira-full-v1", bundle, "0.3.0.dev2", 5) == entry
    with pytest.raises(ValueError, match="already identifies"):
        register(path, "kira-full-v1", bundle, "0.3.1", 5)
    with pytest.raises(ValueError, match="reserved"):
        register(path, "default", bundle, "0.3.0.dev2", 5)
    with pytest.raises(ValueError, match="outside"):
        load_model(path, "kira-full-v1", data_root=tmp_path)
    with pytest.raises(ValueError, match="absolute"):
        load_model(Path("relative.json"), "kira-full-v1", data_root=tmp_path)


def test_named_selection_rejects_runtime_mismatch(registry, monkeypatch):
    path, _, _ = registry
    monkeypatch.setenv("CASANDRA_WEB_MODEL_REGISTRY", str(path))
    monkeypatch.setenv("CASANDRA_WEB_MODEL_NAME", "kira-full-v1")
    monkeypatch.setenv("CASANDRA_WEB_CASANDRA_EXPECTED_VERSION", "casandra 9.0")
    with pytest.raises(ValueError, match="runtime pin"):
        Settings.from_env()


@pytest.mark.parametrize("mode", [
    "complete_genome", "metagenomic", "annotate_cas_genes", "classify_cassette",
])
def test_every_analysis_mode_passes_selected_model(settings, registry, monkeypatch, mode):
    _, bundle, entry = registry
    selected = replace(settings, model_name="kira-full-v1", casandra_model_dir=bundle,
                       casandra_bundle_manifest_sha256=entry["manifest_sha256"])
    store = Store(selected)
    store.initialize()
    service = JobService(selected, store)
    service.submit(JobSubmission(analysis_mode=mode, include_crispr_arrays=False,
                                 sequence=">query\nACGTACGTACGTACGTACGTACGTACGTACGT\n"),
                   "192.0.2.1")
    seen = []

    def capture(self, stage, command, logs, claimed):
        seen.append(command)
        raise WorkerStopping()

    monkeypatch.setattr(Worker, "_run_stage", capture)
    Worker(selected, store=store).run_once()
    assert len(seen) == 1
    assert seen[0][-2:] == ["--model", str(bundle)]
    assert seen[0].count("--model") == 1


def test_preflight_inspects_selected_model_and_detects_later_manifest_change(
    settings, registry, monkeypatch,
):
    _, bundle, entry = registry
    version_file = settings.data_root.parent / "identify-version"
    version_file.write_text("2.0.0")
    selected = replace(settings, model_name="kira-full-v1", casandra_model_dir=bundle,
                       casandra_bundle_id="kira-full-v1",
                       casandra_bundle_manifest_sha256=entry["manifest_sha256"],
                       preflight_scientific_runtime=True,
                       crispridentify_version_file=version_file,
                       crispridentify_expected_version="2.0.0")

    def output(command, label, *, timeout=300):
        if label == "CasAndra version":
            assert "--model" not in command
            return "casandra 0.3.0.dev2"
        assert command[-3:] == ["inspect-model", "--model", str(bundle)]
        return json.dumps({"bundle_id": "kira-full-v1", "bundle_role": "deployment_refit",
                           "integrity": "verified", "cpu_only": True, "offline_inference": True})

    import casandra_web.release_contract as contract
    monkeypatch.setattr(contract, "BUNDLE_ID", "kira-full-v1")
    monkeypatch.setattr(contract, "BUNDLE_MANIFEST_SHA256", entry["manifest_sha256"])
    monkeypatch.setattr(worker_module, "_runtime_output", output)
    worker = Worker(selected)
    worker.validate_runtime()
    (bundle / "manifest.json").write_text("{}")
    with pytest.raises(RuntimeError, match="changed after configuration"):
        worker.validate_runtime()


def test_worker_rejects_output_from_runtime_that_ignores_model_selection(settings, registry):
    _, bundle, entry = registry
    selected = replace(settings, model_name="kira-full-v1", casandra_model_dir=bundle,
                       casandra_bundle_id="kira-full-v1",
                       casandra_bundle_manifest_sha256=entry["manifest_sha256"])
    store = Store(selected)
    store.initialize()
    service = JobService(selected, store)
    created = service.submit(JobSubmission(analysis_mode="annotate_cas_genes",
        sequence=">query\nMTESTMTESTMTESTMTESTMTESTMTESTMTEST\n"), "192.0.2.1")
    # The fake runtime ignores --model and produces internally valid old-bundle output.
    assert Worker(selected, store=store).run_once()
    job = service.get(created.job.job_id, created.access_token)
    assert job.status == "failed"
    assert not job.artifacts

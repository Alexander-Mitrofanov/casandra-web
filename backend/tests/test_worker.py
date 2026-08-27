import json
import sqlite3
import subprocess
import sys
import zipfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from casandra_web.db import (
    CancellationPending,
    CapacityError,
    ClaimedJob,
    LeaseError,
    StorageCapacityError,
    Store,
)
from casandra_web.models import JobSubmission
from casandra_web.service import JobService
from casandra_web.worker import Worker, WorkerStopping


def test_complete_job_builds_visualization_and_safe_bundle(settings):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(
            sequence=">contig_a\nACGTACGTACGTACGTACGTACGTACGTACGTACGT\n",
            filename="genome.fasta",
            gene_mode="auto",
        ),
        "192.0.2.10",
    )
    worker = Worker(settings, store=store, worker_id="test-worker")
    worker.validate_runtime()
    assert worker.run_once() is True

    job = service.get(created.job.job_id, created.access_token)
    assert job.status == "completed"
    assert job.phase == "completed"
    assert job.summary["overview"]["cas_protein_count"] == 1
    assert job.summary["overview"]["crispr_array_count"] == 1
    assert (
        job.summary["cassettes"][0]["nearest_array"]["interpretation"]
        == "coordinate_co_location_only"
    )
    assert "protein_sequence" not in str(job.summary)
    assert any(item.name == "casandra-results.zip" for item in job.artifacts)

    archive_item = next(item for item in job.artifacts if item.name == "casandra-results.zip")
    archive, _metadata = service.artifact_path(
        job.job_id, created.access_token, archive_item.artifact_id
    )
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
    assert "result-summary.json" in names
    assert all("private-logs" not in name for name in names)
    assert all("proteins.jsonl" not in name for name in names)


def test_client_capacity_is_atomic(settings):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    for suffix in ("a", "b"):
        service.submit(
            JobSubmission(sequence=f">{suffix}\nACGTACGTACGT", filename=f"{suffix}.fa"),
            "192.0.2.20",
        )
    with pytest.raises(CapacityError):
        service.submit(
            JobSubmission(sequence=">c\nACGTACGTACGT", filename="c.fa"),
            "192.0.2.20",
        )


def test_cancelled_job_retains_timezone_aware_expiry(settings):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(sequence=">a\nACGTACGTACGT", filename="a.fa"),
        "192.0.2.30",
    )

    job = service.cancel(created.job.job_id, created.access_token)

    expires = datetime.fromisoformat(job.expires_at)
    assert expires.tzinfo is not None
    assert expires > datetime.now(timezone.utc)
    assert store.expired_job_ids() == []


def test_checkpoint_lease_failure_terminates_process(settings, tmp_path, monkeypatch):
    store = Store(settings)
    store.initialize()
    worker = Worker(settings, store=store, worker_id="lease-test")
    recorded: dict[str, subprocess.Popen[bytes]] = {}
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        recorded["process"] = process
        return process

    def lose_lease(*_args, **_kwargs):
        raise LeaseError("test lease loss")

    monkeypatch.setattr("casandra_web.worker.subprocess.Popen", recording_popen)
    monkeypatch.setattr(worker, "_checkpoint", lose_lease)
    logs = tmp_path / "logs"
    logs.mkdir()
    claimed = ClaimedJob("a" * 32, "lease-test", 1, "auto")

    with pytest.raises(LeaseError):
        worker._run_stage(
            "lease-test",
            [sys.executable, "-c", "import time; time.sleep(60)"],
            logs,
            claimed,
        )

    assert recorded["process"].poll() is not None


def test_worker_shutdown_requeues_instead_of_cancelling(settings, monkeypatch):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(sequence=">a\nACGTACGTACGT", filename="a.fa"),
        "192.0.2.40",
    )
    worker = Worker(settings, store=store, worker_id="shutdown-test")

    def stop_stage(*_args, **_kwargs):
        raise WorkerStopping()

    monkeypatch.setattr(worker, "_run_stage", stop_stage)
    assert worker.run_once() is True

    job = service.get(created.job.job_id, created.access_token)
    assert job.status == "queued"
    assert job.cancel_requested is False
    assert store.get_job(job.job_id)["attempt"] == 0


def test_cancelled_submissions_still_count_toward_rate_limit(settings):
    limited = replace(settings, max_active_jobs_per_client=1, max_submissions_per_window=3)
    store = Store(limited)
    store.initialize()
    service = JobService(limited, store)
    for index in range(3):
        created = service.submit(
            JobSubmission(sequence=f">r{index}\nACGTACGTACGT", filename=f"r{index}.fa"),
            "192.0.2.50",
        )
        service.cancel(created.job.job_id, created.access_token)

    with pytest.raises(CapacityError, match="recent submission"):
        service.submit(
            JobSubmission(sequence=">blocked\nACGTACGTACGT", filename="blocked.fa"),
            "192.0.2.50",
        )


def test_retained_job_limit_includes_cancelled_jobs(settings):
    limited = replace(
        settings,
        max_retained_jobs=1,
        max_submissions_per_window=10,
    )
    store = Store(limited)
    store.initialize()
    service = JobService(limited, store)
    created = service.submit(
        JobSubmission(sequence=">kept\nACGTACGTACGT", filename="kept.fa"),
        "192.0.2.60",
    )
    service.cancel(created.job.job_id, created.access_token)

    with pytest.raises(StorageCapacityError, match="retained-job"):
        service.submit(
            JobSubmission(sequence=">extra\nACGTACGTACGT", filename="extra.fa"),
            "192.0.2.61",
        )


def test_free_space_floor_rejects_before_materializing_job_input(settings):
    limited = replace(settings, min_free_bytes=10**30)
    store = Store(limited)
    store.initialize()
    service = JobService(limited, store)

    with pytest.raises(StorageCapacityError, match="free storage"):
        service.submit(
            JobSubmission(sequence=">space\nACGTACGTACGT", filename="space.fa"),
            "192.0.2.62",
        )
    assert not (limited.data_root / "jobs").exists()


def test_completion_cannot_win_after_cancellation(settings):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(sequence=">race\nACGTACGTACGT", filename="race.fa"),
        "192.0.2.70",
    )
    claimed = store.claim_next("race-worker")
    assert claimed is not None
    store.request_cancel(created.job.job_id)

    with pytest.raises(CancellationPending):
        store.complete(claimed, {"must_not_publish": True}, [])
    assert store.list_artifacts(created.job.job_id) == []
    store.mark_cancelled(claimed)
    assert store.get_job(created.job.job_id)["status"] == "cancelled"


def test_absolute_deadline_terminates_queued_job_but_preserves_failure(settings):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(sequence=">deadline\nACGTACGTACGT", filename="deadline.fa"),
        "192.0.2.80",
    )
    overdue = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute(
            "UPDATE jobs SET deadline_at=? WHERE job_id=?",
            (overdue, created.job.job_id),
        )
    store.expire_overdue_jobs()

    job = service.get(created.job.job_id, created.access_token)
    assert job.status == "failed"
    assert job.error.code == "job_deadline_exceeded"
    assert datetime.fromisoformat(job.expires_at) > datetime.now(timezone.utc)


def test_full_array_artifact_survives_interactive_projection_limit(settings, monkeypatch):
    monkeypatch.setattr("casandra_web.summary._MAX_ARRAYS", 0)
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(
            sequence=">projection\nACGTACGTACGTACGTACGTACGTACGTACGT\n",
            filename="projection.fa",
        ),
        "192.0.2.90",
    )
    assert Worker(settings, store=store, worker_id="projection-worker").run_once() is True

    job = service.get(created.job.job_id, created.access_token)
    assert job.summary["overview"]["crispr_array_count"] == 1
    assert job.summary["crispr_arrays"] == []
    assert job.summary["detail_truncated"]["crispr_arrays"] is True
    assert job.summary["cassettes"][0]["nearest_array"]["array_id"] == "CRISPR-projection"
    item = next(artifact for artifact in job.artifacts if artifact.name == "crispr-arrays.json")
    path, _ = service.artifact_path(job.job_id, created.access_token, item.artifact_id)
    assert len(json.loads(path.read_text(encoding="utf-8"))["arrays"]) == 1

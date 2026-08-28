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
            analysis_mode="complete_genome",
            sequence=">contig_a\nACGTACGTACGTACGTACGTACGTACGTACGTACGT\n",
            filename="genome.fasta",
            include_crispr_arrays=True,
        ),
        "192.0.2.10",
    )
    assert service.records_path(created.job.job_id).is_dir()
    assert len(list(service.records_path(created.job.job_id).glob("*.fasta"))) == 1
    worker = Worker(settings, store=store, worker_id="test-worker")
    worker.validate_runtime()
    assert worker.run_once() is True

    job = service.get(created.job.job_id, created.access_token)
    assert job.status == "completed"
    assert job.phase == "completed"
    assert job.summary["overview"]["cas_protein_count"] == 1
    assert job.summary["overview"]["crispr_array_count"] == 1
    assert job.summary["provenance"]["casandra_program_version"] == "0.3.0.dev0"
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


def test_new_complete_genome_uses_single_mode_and_skips_unrequested_arrays(settings):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(
            analysis_mode="complete_genome",
            sequence=">genome\nACGTACGTACGTACGTACGTACGTACGTACGT\n",
        ),
        "192.0.2.11",
    )
    stored = store.get_job(created.job.job_id)
    assert stored["gene_mode"] == "auto"
    assert stored["requested_gene_mode"] == "single"
    assert not service.records_path(created.job.job_id).exists()

    assert Worker(settings, store=store, worker_id="single-worker").run_once() is True
    job = service.get(created.job.job_id, created.access_token)
    assert job.options.gene_mode == "single"
    assert job.summary["include_crispr_arrays"] is False
    assert job.summary["overview"]["crispr_array_count"] == 0
    assert job.summary["provenance"]["array_detection"]["status"] == "not_requested"
    assert "CRISPRidentify" not in " ".join(job.summary["warnings"])
    assert all(item.name != "crispr-arrays.json" for item in job.artifacts)


def test_annotate_mode_returns_every_protein_and_accepts_more_than_genome_cap(settings):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    records = [">cas2_without_type\nMKTW"]
    records.extend(f">protein_{index}\nMKTW" for index in range(24))
    records.append(">noncas_control\nACDX*")
    created = service.submit(
        JobSubmission(
            analysis_mode="annotate_cas_genes",
            sequence="\n".join(records),
            filename="many-proteins.faa",
        ),
        "192.0.2.12",
    )
    assert not service.records_path(created.job.job_id).exists()

    assert Worker(settings, store=store, worker_id="protein-worker").run_once() is True
    job = service.get(created.job.job_id, created.access_token)
    assert job.status == "completed"
    assert job.input.sequence_unit == "aa"
    assert job.input.base_count is None
    assert job.summary["analysis_mode"] == "annotate_cas_genes"
    assert job.summary["overview"]["protein_count"] == 26
    assert job.summary["overview"]["wall_seconds"] == 0.02
    assert len(job.summary["protein_predictions"]) == 26
    assert job.summary["protein_predictions"][0]["result"] == "Cas2"
    assert job.summary["protein_predictions"][0]["cas_family"] == "Cas2"
    assert job.summary["protein_predictions"][0]["type"] is None
    assert job.summary["protein_predictions"][0]["profile"] == "C25_Cas2_1"
    assert job.summary["protein_predictions"][1]["result"] == "Cas3"
    assert job.summary["protein_predictions"][-1]["result"] == "no cas"
    assert job.summary["protein_predictions"][-1]["is_cas"] is False
    assert job.summary["provenance"]["casandra_bundle_id"] == "fake-bundle"
    assert job.summary["provenance"]["casandra_model_id"] == "fake-protein-model"
    assert job.summary["provenance"]["casandra_program_version"] == "0.3.0.dev0"
    assert {item.name for item in job.artifacts}.issuperset(
        {
            "protein-predictions.jsonl",
            "casandra-run.json",
            "casandra-manifest.json",
        }
    )
    predictions_artifact = next(
        item for item in job.artifacts if item.name == "protein-predictions.jsonl"
    )
    predictions_path, _metadata = service.artifact_path(
        job.job_id, created.access_token, predictions_artifact.artifact_id
    )
    artifact_rows = [
        json.loads(line) for line in predictions_path.read_text().splitlines()
    ]
    assert artifact_rows[0]["result"] == "Cas2"
    assert artifact_rows[-1]["result"] == "no cas"


@pytest.mark.parametrize(
    "protein_id",
    ["annotation_model_mismatch", "annotation_checksum_mismatch"],
)
def test_annotation_corrupt_provenance_or_checksum_cannot_publish(settings, protein_id):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(
            analysis_mode="annotate_cas_genes",
            sequence=f">{protein_id}\nMKTW\n",
        ),
        f"test-{protein_id}",
    )

    assert Worker(settings, store=store, worker_id=f"worker-{protein_id}").run_once() is True
    job = service.get(created.job.job_id, created.access_token)
    assert job.status == "failed"
    assert job.error.code == "result_validation_failed"
    assert job.summary is None
    assert job.artifacts == []


def test_annotation_positive_without_family_identity_cannot_publish(settings):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(
            analysis_mode="annotate_cas_genes",
            sequence=">annotation_missing_family\nMKTW\n",
        ),
        "family-validation-client",
    )

    assert Worker(settings, store=store, worker_id="family-validation-worker").run_once()
    job = service.get(created.job.job_id, created.access_token)
    assert job.status == "failed"
    assert job.error.code == "result_validation_failed"
    assert job.artifacts == []


@pytest.mark.parametrize(
    "protein_id", ["annotation_missing_result", "annotation_bad_result"]
)
def test_annotation_missing_or_contradictory_result_cannot_publish(
    settings, protein_id
):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(
            analysis_mode="annotate_cas_genes",
            sequence=f">{protein_id}\nMKTW\n",
        ),
        f"result-validation-{protein_id}",
    )

    assert Worker(
        settings, store=store, worker_id=f"result-validation-{protein_id}"
    ).run_once()
    job = service.get(created.job.job_id, created.access_token)
    assert job.status == "failed"
    assert job.error.code == "result_validation_failed"
    assert job.summary is None
    assert job.artifacts == []


def test_classify_cassette_uses_ordered_proteins_and_reports_no_cas(settings):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(
            analysis_mode="classify_cassette",
            sequence=">noncas_first\nMKTW\n>noncas_second\nACDX*\n",
        ),
        "192.0.2.13",
    )
    assert not service.records_path(created.job.job_id).exists()

    assert Worker(settings, store=store, worker_id="cassette-worker").run_once() is True
    job = service.get(created.job.job_id, created.access_token)
    classification = job.summary["cassette_classification"]
    assert classification["result"] == "no cas"
    assert classification["cas_gene_count"] == 0
    assert classification["order_used_for_architecture"] is True
    assert classification["coordinates_available"] is False
    assert classification["confidence_is_probability"] is False
    assert job.summary["overview"]["wall_seconds"] == 0.01
    assert job.summary["provenance"]["casandra_bundle_id"] == "fake-bundle"
    assert job.summary["provenance"]["casandra_bundle_role"] == "deployment_refit"
    assert job.summary["provenance"]["casandra_manifest_sha256"] == "a" * 64
    assert job.summary["provenance"]["casandra_model_id"] == "fake-protein-model"
    assert job.summary["provenance"]["casandra_program_version"] == "0.3.0.dev0"
    assert [row["protein_id"] for row in job.summary["protein_predictions"]] == [
        "noncas_first",
        "noncas_second",
    ]
    assert [row["result"] for row in job.summary["protein_predictions"]] == [
        "no cas",
        "no cas",
    ]
    assert any(item.name == "cassette-classification.json" for item in job.artifacts)


def test_cassette_model_provenance_mismatch_cannot_publish_results(settings):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(
            analysis_mode="classify_cassette",
            sequence=">model_mismatch\nMKTW\n",
        ),
        "192.0.2.131",
    )

    assert Worker(settings, store=store, worker_id="provenance-worker").run_once() is True
    job = service.get(created.job.job_id, created.access_token)
    assert job.status == "failed"
    assert job.error.code == "result_validation_failed"
    assert job.summary is None
    assert job.artifacts == []


@pytest.mark.parametrize(
    "protein_id",
    [
        "cassette_missing_bundle_id",
        "cassette_missing_bundle_role",
        "cassette_bad_program",
        "cassette_bad_program_version",
        "cassette_bundle_mismatch",
        "cassette_input_kind_mismatch",
        "cassette_input_name_mismatch",
        "cassette_input_sha_mismatch",
        "cassette_online_inference",
        "cassette_arrays_enabled",
        "cassette_negative_wall_time",
    ],
)
def test_malformed_cassette_run_provenance_cannot_publish(settings, protein_id):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(
            analysis_mode="classify_cassette",
            sequence=f">{protein_id}\nMKTW\n",
        ),
        f"malformed-{protein_id}",
    )

    assert Worker(
        settings, store=store, worker_id=f"worker-{protein_id}"
    ).run_once()
    job = service.get(created.job.job_id, created.access_token)
    assert job.status == "failed"
    assert job.error.code == "result_validation_failed"
    assert job.summary is None
    assert job.artifacts == []


def test_metagenomic_summary_groups_detection_counts_per_sequence(settings):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(
            analysis_mode="metagenomic",
            sequence=">sample_a\nACGTACGTACGT\n>sample_b\nACGTACGTACGTACGT\n",
        ),
        "192.0.2.14",
    )
    assert not service.records_path(created.job.job_id).exists()

    assert Worker(settings, store=store, worker_id="meta-worker").run_once() is True
    job = service.get(created.job.job_id, created.access_token)
    assert job.options.gene_mode == "meta"
    assert job.summary["analysis_mode"] == "metagenomic"
    assert job.summary["sequence_results"] == [
        {
            "sequence_id": "sample_a",
            "length_bp": 12,
            "gene_count": 1,
            "cas_gene_count": 1,
            "cas_protein_count": 1,
            "cassette_count": 1,
        },
        {
            "sequence_id": "sample_b",
            "length_bp": 16,
            "gene_count": 1,
            "cas_gene_count": 1,
            "cas_protein_count": 1,
            "cassette_count": 1,
        },
    ]
    assert job.summary["provenance"]["gene_calling"]["requested_mode"] == "meta"
    assert job.summary["provenance"]["array_detection"]["status"] == "not_requested"


def test_legacy_database_migration_preserves_gene_mode_and_array_execution(settings):
    settings.prepare()
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute(
            """
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY,
                token_digest TEXT NOT NULL,
                client_digest TEXT NOT NULL,
                status TEXT NOT NULL,
                phase TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                expires_at TEXT,
                deadline_at TEXT NOT NULL,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                attempt INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL,
                worker_id TEXT,
                lease_expires REAL,
                filename TEXT NOT NULL,
                record_count INTEGER NOT NULL,
                base_count INTEGER NOT NULL,
                input_sha256 TEXT NOT NULL,
                source_ids_json TEXT NOT NULL,
                gene_mode TEXT NOT NULL CHECK(gene_mode IN ('auto','meta')),
                summary_json TEXT,
                error_code TEXT,
                error_message TEXT
            )
            """
        )
        for ordinal, gene_mode in enumerate(("auto", "meta"), start=1):
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, token_digest, client_digest, status, phase, created_at,
                    updated_at, deadline_at, max_attempts, filename, record_count,
                    base_count, input_sha256, source_ids_json, gene_mode
                ) VALUES (?, 'token', 'client', 'queued', 'queued', ?, ?, ?, 2,
                    'legacy.fa', 1, 4, ?, '["legacy"]', ?)
                """,
                (
                    str(ordinal) * 32,
                    f"2026-01-0{ordinal}T00:00:00+00:00",
                    f"2026-01-0{ordinal}T00:00:00+00:00",
                    "2099-01-01T00:00:00+00:00",
                    "a" * 64,
                    gene_mode,
                ),
            )

    store = Store(settings)
    store.initialize()
    with sqlite3.connect(settings.database_path) as connection:
        rows = connection.execute(
            "SELECT gene_mode, requested_gene_mode, analysis_mode, include_crispr_arrays "
            "FROM jobs ORDER BY created_at"
        ).fetchall()
    assert rows == [
        ("auto", None, "complete_genome", 1),
        ("meta", None, "complete_genome", 1),
    ]

    first = store.claim_next("legacy-worker")
    assert first is not None
    assert first.gene_mode == "auto"
    assert first.analysis_mode == "complete_genome"
    assert first.include_crispr_arrays is True


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

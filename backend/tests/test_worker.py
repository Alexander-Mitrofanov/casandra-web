import csv
import hashlib
import json
import sqlite3
import subprocess
import sys
import zipfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

import casandra_web.worker as worker_module
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


def _artifact_path(service, job, access_token, name):
    item = next(artifact for artifact in job.artifacts if artifact.name == name)
    path, _metadata = service.artifact_path(job.job_id, access_token, item.artifact_id)
    return path


def _fasta_records(path):
    records = []
    identifier = None
    sequence = []
    for raw_line in path.read_text(encoding="ascii").splitlines():
        if raw_line.startswith(">"):
            if identifier is not None:
                records.append((identifier, "".join(sequence)))
            identifier = raw_line[1:].split(maxsplit=1)[0]
            sequence = []
        elif raw_line:
            assert identifier is not None
            sequence.append(raw_line)
    if identifier is not None:
        records.append((identifier, "".join(sequence)))
    return records


def _reverse_complement(sequence):
    complement = str.maketrans("ACGTRYSWKMBDHVN", "TGCAYRSWMKVHDBN")
    return sequence.translate(complement)[::-1]


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
    assert {item.name for item in job.artifacts}.issuperset(
        {
            "casandra-results.json",
            "casandra-results.csv",
            "cas-proteins.faa",
            "cas-coding-sequences.fna",
            "crispr-arrays.fna",
            "crispr-components.fna",
        }
    )

    detail_item = next(item for item in job.artifacts if item.name == "casandra-results.json")
    assert detail_item.role == "results"
    assert detail_item.format == "json"
    assert detail_item.scope == "all_features"
    detail_path, _ = service.artifact_path(
        job.job_id, created.access_token, detail_item.artifact_id
    )
    detail = json.loads(detail_path.read_text(encoding="utf-8"))
    assert detail["analysis_mode"] == "complete_genome"
    assert detail["feature_count"] == 3
    assert detail["feature_counts"] == {
        "cas_gene": 1,
        "cassette": 1,
        "crispr_array": 1,
    }
    assert [feature["kind"] for feature in detail["features"]] == [
        "cas_gene",
        "crispr_array",
        "cassette",
    ]
    by_kind = {
        kind: [feature for feature in detail["features"] if feature["kind"] == kind]
        for kind in ("cas_gene", "cassette", "crispr_array")
    }
    assert {kind: len(rows) for kind, rows in by_kind.items()} == {
        "cas_gene": 1,
        "cassette": 1,
        "crispr_array": 1,
    }
    gene_sequences = {item["key"]: item for item in by_kind["cas_gene"][0]["sequences"]}
    assert set(gene_sequences) == {"protein", "coding_dna", "source_forward_dna"}
    assert by_kind["cas_gene"][0]["result"] == "Cas3"
    assert by_kind["cas_gene"][0]["cas_family"] == "Cas3"
    assert gene_sequences["protein"]["sha256"] == hashlib.sha256(b"MTEST").hexdigest()
    array = by_kind["crispr_array"][0]
    assert array["consensus_repeat"] == "ACGT"
    assert array["spacers"] == ["CGTA", "GTAC"]

    csv_path = _artifact_path(service, job, created.access_token, "casandra-results.csv")
    with csv_path.open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert [row["feature_kind"] for row in csv_rows] == [
        "cas_gene",
        "crispr_array",
        "cassette",
    ]
    assert [row["feature_ref"] for row in csv_rows] == [
        feature["feature_ref"] for feature in detail["features"]
    ]

    assert _fasta_records(
        _artifact_path(service, job, created.access_token, "cas-proteins.faa")
    ) == [("contig_a_cas1", "MTEST")]
    assert _fasta_records(
        _artifact_path(service, job, created.access_token, "cas-coding-sequences.fna")
    ) == [("contig_a_cas1", "ACGTACGTACGTACGTACGTACGTACGTAC")]
    assert _fasta_records(
        _artifact_path(service, job, created.access_token, "crispr-arrays.fna")
    ) == [("CRISPR-contig_a", "CGTACGT")]
    assert _fasta_records(
        _artifact_path(service, job, created.access_token, "crispr-components.fna")
    ) == [
        ("CRISPR-contig_a|consensus_repeat", "ACGT"),
        ("CRISPR-contig_a|spacer=1", "CGTA"),
        ("CRISPR-contig_a|spacer=2", "GTAC"),
    ]

    archive_item = next(item for item in job.artifacts if item.name == "casandra-results.zip")
    archive, _metadata = service.artifact_path(
        job.job_id, created.access_token, archive_item.artifact_id
    )
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
    assert "result-summary.json" in names
    assert {
        "exports/casandra-results.json",
        "exports/casandra-results.csv",
        "exports/cas-proteins.faa",
        "exports/cas-coding-sequences.fna",
        "exports/crispr-arrays.fna",
        "exports/crispr-components.fna",
    }.issubset(names)
    assert all("private-logs" not in name for name in names)
    assert all("proteins.jsonl" not in name for name in names)


def test_runtime_preflight_binds_public_scientific_identity(settings, monkeypatch):
    version_file = settings.data_root.parent / "crispridentify-version"
    version_file.write_text("2.0.0\n", encoding="ascii")
    configured = replace(
        settings,
        preflight_scientific_runtime=True,
        crispridentify_version_file=version_file,
        crispridentify_expected_version="2.0.0",
    )

    def runtime_output(_command, label, *, timeout=300):
        del timeout
        if label == "CasAndra model":
            return json.dumps(
                {
                    "bundle_id": "fake-bundle",
                    "bundle_role": "deployment_refit",
                    "integrity": "verified",
                    "cpu_only": True,
                    "offline_inference": True,
                }
            )
        if label == "CasAndra version":
            return "casandra 0.3.0.dev0"
        raise AssertionError(f"unexpected runtime check: {label}")

    monkeypatch.setattr(worker_module, "_runtime_output", runtime_output)
    Worker(configured).validate_runtime()

    mismatched = replace(configured, casandra_bundle_id="unexpected-bundle")
    with pytest.raises(RuntimeError, match="bundle does not match"):
        Worker(mismatched).validate_runtime()


def test_complete_export_orients_reverse_strand_coding_sequence(settings):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    source = "ACGTTTCCAAGGATCCTAACGGTTAACCGGTTACGT"
    created = service.submit(
        JobSubmission(
            analysis_mode="complete_genome",
            sequence=f">export_reverse_gene\n{source}\n",
        ),
        "reverse-export-client",
    )

    assert Worker(settings, store=store, worker_id="reverse-export-worker").run_once()
    job = service.get(created.job.job_id, created.access_token)
    assert job.status == "completed"
    details = json.loads(
        _artifact_path(service, job, created.access_token, "casandra-results.json").read_text(
            encoding="utf-8"
        )
    )
    gene = next(feature for feature in details["features"] if feature["kind"] == "cas_gene")
    sequences = {item["key"]: item for item in gene["sequences"]}
    forward = source[:30]
    coding = _reverse_complement(forward)
    assert gene["strand"] == "-"
    assert sequences["source_forward_dna"]["sequence"] == forward
    assert sequences["coding_dna"]["sequence"] == coding
    assert sequences["coding_dna"]["orientation"] == "coding_strand_5_to_3"
    assert _fasta_records(
        _artifact_path(service, job, created.access_token, "cas-coding-sequences.fna")
    ) == [("export_reverse_gene_cas1", coding)]


def test_source_inconsistent_coding_sequence_cannot_publish_exports(settings):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(
            analysis_mode="complete_genome",
            sequence=">export_coding_mismatch\nACGTTTCCAAGGATCCTAACGGTTAACCGGTTACGT\n",
        ),
        "coding-mismatch-client",
    )

    assert Worker(settings, store=store, worker_id="coding-mismatch-worker").run_once()
    job = service.get(created.job.job_id, created.access_token)
    assert job.status == "failed"
    assert job.error.code == "result_validation_failed"
    assert job.summary is None
    assert job.artifacts == []
    attempts = list((service.job_root(job.job_id) / "output").glob("attempt-*"))
    assert len(attempts) == 1
    assert not (attempts[0] / "exports").exists()
    assert not list(attempts[0].glob(".exports.*"))


def test_export_ids_are_csv_safe_and_lossless_in_json_and_fasta(settings):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(
            analysis_mode="complete_genome",
            sequence=">csv_formula\nACGTACGTACGTACGTACGTACGTACGTACGT\n",
            include_crispr_arrays=True,
        ),
        "csv-export-client",
    )

    assert Worker(settings, store=store, worker_id="csv-export-worker").run_once()
    job = service.get(created.job.job_id, created.access_token)
    details = json.loads(
        _artifact_path(service, job, created.access_token, "casandra-results.json").read_text(
            encoding="utf-8"
        )
    )
    array = next(feature for feature in details["features"] if feature["kind"] == "crispr_array")
    assert array["feature_id"] == " =2+5"

    with _artifact_path(service, job, created.access_token, "casandra-results.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        array_row = next(
            row for row in csv.DictReader(handle) if row["feature_kind"] == "crispr_array"
        )
    assert array_row["feature_id"] == "' =2+5"
    assert array_row["feature_ref"] == "crispr_array:csv_formula: =2+5"
    component_ids = [
        identifier
        for identifier, _sequence in _fasta_records(
            _artifact_path(service, job, created.access_token, "crispr-components.fna")
        )
    ]
    assert component_ids == [
        "%20=2+5|consensus_repeat",
        "%20=2+5|spacer=1",
        "%20=2+5|spacer=2",
    ]


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


def test_complete_genome_accepts_rejected_positive_profile_evidence(settings):
    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(
        JobSubmission(
            analysis_mode="complete_genome",
            sequence=">rejected_profile\nACGTACGTACGTACGTACGTACGTACGTACGT\n",
        ),
        "192.0.2.111",
    )

    assert Worker(settings, store=store, worker_id="profile-evidence-worker").run_once()
    job = service.get(created.job.job_id, created.access_token)

    assert job.status == "completed"
    assert job.summary["overview"]["cas_protein_count"] == 1
    assert [row["result"] for row in job.summary["cas_proteins"]] == ["Cas3"]
    details = json.loads(
        _artifact_path(service, job, created.access_token, "casandra-results.json").read_text(
            encoding="utf-8"
        )
    )
    assert [row["result"] for row in details["features"] if row["kind"] == "cas_gene"] == [
        "Cas3"
    ]


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
            "casandra-results.json",
            "casandra-results.csv",
            "all-proteins.faa",
            "cas-proteins.faa",
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
    artifact_rows = [json.loads(line) for line in predictions_path.read_text().splitlines()]
    assert artifact_rows[0]["result"] == "Cas2"
    assert artifact_rows[-1]["result"] == "no cas"
    details_artifact = next(item for item in job.artifacts if item.name == "casandra-results.json")
    details_path, _ = service.artifact_path(
        job.job_id, created.access_token, details_artifact.artifact_id
    )
    details = json.loads(details_path.read_text(encoding="utf-8"))
    proteins = [item for item in details["features"] if item["kind"] == "protein"]
    assert [item["feature_id"] for item in proteins] == [
        row.removeprefix(">").split("\n", 1)[0] for row in records
    ]
    assert proteins[0]["sequences"][0]["sequence"] == "MKTW"
    assert proteins[-1]["result"] == "no cas"
    expected_ids = [row.removeprefix(">").split("\n", 1)[0] for row in records]
    assert [
        identifier
        for identifier, _sequence in _fasta_records(
            _artifact_path(service, job, created.access_token, "all-proteins.faa")
        )
    ] == expected_ids
    assert [
        identifier
        for identifier, _sequence in _fasta_records(
            _artifact_path(service, job, created.access_token, "cas-proteins.faa")
        )
    ] == expected_ids[:-1]


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


@pytest.mark.parametrize("protein_id", ["annotation_missing_result", "annotation_bad_result"])
def test_annotation_missing_or_contradictory_result_cannot_publish(settings, protein_id):
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

    assert Worker(settings, store=store, worker_id=f"result-validation-{protein_id}").run_once()
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
    assert {item.name for item in job.artifacts}.issuperset(
        {
            "casandra-results.json",
            "casandra-results.csv",
            "cassette-proteins.faa",
            "cassette-cas-proteins.faa",
        }
    )
    assert _fasta_records(
        _artifact_path(service, job, created.access_token, "cassette-proteins.faa")
    ) == [("noncas_first", "MKTW"), ("noncas_second", "ACDX*")]
    assert (
        _fasta_records(
            _artifact_path(service, job, created.access_token, "cassette-cas-proteins.faa")
        )
        == []
    )
    details = json.loads(
        _artifact_path(service, job, created.access_token, "casandra-results.json").read_text(
            encoding="utf-8"
        )
    )
    assert [feature["kind"] for feature in details["features"]] == [
        "protein",
        "protein",
        "cassette",
    ]


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

    assert Worker(settings, store=store, worker_id=f"worker-{protein_id}").run_once()
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
        max_queued_jobs=1,
        max_active_jobs=2,
        max_retained_jobs=2,
        max_submissions_per_window=10,
    )
    store = Store(limited)
    store.initialize()
    service = JobService(limited, store)
    for index in range(2):
        created = service.submit(
            JobSubmission(sequence=f">kept{index}\nACGTACGTACGT", filename="kept.fa"),
            f"192.0.2.{60 + index}",
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
    details = json.loads(
        _artifact_path(service, job, created.access_token, "casandra-results.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        len([feature for feature in details["features"] if feature["kind"] == "crispr_array"]) == 1
    )

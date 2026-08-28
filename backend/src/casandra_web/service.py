"""Application service boundary for validated jobs and capability authorization."""

from __future__ import annotations

import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .db import Store
from .fasta import NormalizedFasta, normalize_fasta, normalize_protein_fasta
from .models import (
    AnalysisMode,
    ArtifactView,
    ErrorView,
    GeneMode,
    InputSummary,
    JobCreated,
    JobOptions,
    JobPhase,
    JobStatus,
    JobSubmission,
    JobView,
)
from .security import (
    client_digest,
    new_access_token,
    new_job_id,
    safe_display_filename,
    token_digest,
    token_matches,
)

_JOB_ID = re.compile(r"[0-9a-f]{32}")


def _artifact_presentation(name: str) -> dict[str, str | None]:
    preferred = {
        "casandra-results.json": ("results", "json", "all_features", None),
        "casandra-results.csv": ("results", "csv", "all_features", None),
        "all-proteins.faa": ("sequences", "fasta", "all_proteins", "protein"),
        "cassette-proteins.faa": (
            "sequences",
            "fasta",
            "ordered_cassette_proteins",
            "protein",
        ),
        "cassette-cas-proteins.faa": (
            "sequences",
            "fasta",
            "cassette_cas_proteins",
            "protein",
        ),
        "cas-proteins.faa": ("sequences", "fasta", "cas_proteins", "protein"),
        "cas-coding-sequences.fna": (
            "sequences",
            "fasta",
            "cas_coding_sequences",
            "dna",
        ),
        "crispr-arrays.fna": ("sequences", "fasta", "crispr_arrays", "dna"),
        "crispr-components.fna": (
            "sequences",
            "fasta",
            "crispr_repeats_and_spacers",
            "dna",
        ),
    }
    if name in preferred:
        role, output_format, scope, molecule = preferred[name]
        return {
            "role": role,
            "format": output_format,
            "scope": scope,
            "molecule": molecule,
        }
    if name == "casandra-results.zip":
        return {"role": "bundle", "format": "zip", "scope": "all_artifacts", "molecule": None}
    suffix = Path(name).suffix.lower()
    output_format = {
        ".json": "json",
        ".jsonl": "json",
        ".csv": "csv",
        ".tsv": "tsv",
        ".gff3": "gff3",
        ".zip": "zip",
        ".faa": "fasta",
        ".fna": "fasta",
        ".fasta": "fasta",
    }.get(suffix, "other")
    return {
        "role": "technical",
        "format": output_format,
        "scope": None,
        "molecule": None,
    }


class AuthorizationError(RuntimeError):
    pass


class NotFoundError(RuntimeError):
    pass


class ExpiredError(RuntimeError):
    pass


class JobService:
    def __init__(self, settings: Settings, store: Store | None = None):
        self.settings = settings
        self.store = store or Store(settings)

    @property
    def jobs_root(self) -> Path:
        path = self.settings.data_root / "jobs"
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)
        return path

    def job_root(self, job_id: str) -> Path:
        if _JOB_ID.fullmatch(job_id) is None:
            raise NotFoundError("Job not found")
        return self.jobs_root / job_id

    def normalized_input_path(self, job_id: str) -> Path:
        return self.job_root(job_id) / "input" / "genome.fasta"

    def protein_input_path(self, job_id: str) -> Path:
        return self.job_root(job_id) / "input" / "proteins.faa"

    def analysis_input_path(self, job_id: str, analysis_mode: str) -> Path:
        if analysis_mode in {
            AnalysisMode.annotate_cas_genes.value,
            AnalysisMode.classify_cassette.value,
        }:
            return self.protein_input_path(job_id)
        return self.normalized_input_path(job_id)

    def records_path(self, job_id: str) -> Path:
        return self.job_root(job_id) / "input" / "records"

    def submit(self, submission: JobSubmission, client_address: str) -> JobCreated:
        protein_input = submission.analysis_mode in {
            AnalysisMode.annotate_cas_genes,
            AnalysisMode.classify_cassette,
        }
        if protein_input:
            normalized = normalize_protein_fasta(
                submission.sequence,
                max_request_bytes=self.settings.max_request_bytes,
                max_total_residues=self.settings.max_total_residues,
                max_record_residues=self.settings.max_protein_residues,
                max_records=self.settings.max_protein_records,
                max_header_characters=self.settings.max_header_characters,
            )
        else:
            normalized = normalize_fasta(
                submission.sequence,
                max_request_bytes=self.settings.max_request_bytes,
                max_total_bases=self.settings.max_total_bases,
                max_record_bases=self.settings.max_record_bases,
                max_records=self.settings.max_records,
                max_header_characters=self.settings.max_header_characters,
            )
        job_id = new_job_id()
        token = new_access_token()
        client_key = client_digest(client_address, self.settings.token_pepper)
        self.store.check_admission(client_key, normalized.base_count)
        root = self.job_root(job_id)
        try:
            self._write_input(
                root,
                normalized,
                input_filename="proteins.faa" if protein_input else "genome.fasta",
                write_records=submission.include_crispr_arrays,
            )
            job = self.store.create_job(
                job_id=job_id,
                token_digest=token_digest(token, self.settings.token_pepper),
                client_digest=client_key,
                filename=safe_display_filename(submission.filename),
                record_count=len(normalized.records),
                base_count=normalized.base_count,
                input_sha256=normalized.sha256,
                source_ids=(record.source_id for record in normalized.records),
                gene_mode=(submission.gene_mode or GeneMode.auto).value,
                analysis_mode=submission.analysis_mode.value,
                include_crispr_arrays=submission.include_crispr_arrays,
            )
        except Exception:
            self._remove_job_tree(root)
            raise
        return JobCreated(access_token=token, job=self._view(job))

    def authorize(self, job_id: str, token: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if job is None:
            raise NotFoundError("Job not found")
        if not token_matches(token, str(job["token_digest"]), self.settings.token_pepper):
            raise AuthorizationError("The job access token is invalid")
        expires_at = job.get("expires_at")
        if expires_at:
            try:
                expired = datetime.fromisoformat(str(expires_at)) <= datetime.now(timezone.utc)
            except ValueError as error:
                raise RuntimeError("stored job expiry is invalid") from error
            if expired:
                raise ExpiredError("Job results have expired")
        return job

    def get(self, job_id: str, token: str) -> JobView:
        return self._view(self.authorize(job_id, token))

    def cancel(self, job_id: str, token: str) -> JobView:
        self.authorize(job_id, token)
        job = self.store.request_cancel(job_id)
        if job is None:
            raise NotFoundError("Job not found")
        return self._view(job)

    def artifact_path(
        self, job_id: str, token: str, artifact_id: str
    ) -> tuple[Path, dict[str, Any]]:
        self.authorize(job_id, token)
        artifact = self.store.get_artifact(job_id, artifact_id)
        if artifact is None:
            raise NotFoundError("Artifact not found")
        root = self.job_root(job_id).resolve()
        candidate = root / str(artifact["relative_path"])
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as error:
            raise NotFoundError("Artifact not found") from error
        if (
            not resolved.is_file()
            or resolved.is_symlink()
            or resolved.stat().st_size != int(artifact["size_bytes"])
        ):
            raise NotFoundError("Artifact not found")
        return resolved, artifact

    def cleanup_expired(self) -> int:
        self.store.expire_overdue_jobs()
        removed = 0
        for job_id in self.store.expired_job_ids():
            root = self.job_root(job_id)
            self._remove_job_tree(root)
            self.store.delete_job(job_id)
            removed += 1
        return removed

    def _view(self, job: dict[str, Any]) -> JobView:
        analysis_mode = AnalysisMode(
            str(job.get("analysis_mode") or AnalysisMode.complete_genome.value)
        )
        protein_input = analysis_mode in {
            AnalysisMode.annotate_cas_genes,
            AnalysisMode.classify_cassette,
        }
        effective_gene_mode = str(job.get("requested_gene_mode") or job["gene_mode"])
        artifacts = [
            ArtifactView(
                artifact_id=str(item["artifact_id"]),
                name=str(item["name"]),
                size_bytes=int(item["size_bytes"]),
                sha256=str(item["sha256"]),
                media_type=str(item["media_type"]),
                download_url=(
                    f"/casandra/api/v1/jobs/{job['job_id']}/artifacts/{item['artifact_id']}"
                ),
                **_artifact_presentation(str(item["name"])),
            )
            for item in self.store.list_artifacts(str(job["job_id"]))
        ]
        error = None
        if job.get("error_code"):
            error = ErrorView(
                code=str(job["error_code"]),
                message=str(job.get("error_message") or "The analysis failed."),
            )
        return JobView(
            job_id=str(job["job_id"]),
            status=JobStatus(str(job["status"])),
            phase=JobPhase(str(job["phase"])),
            created_at=str(job["created_at"]),
            updated_at=str(job["updated_at"]),
            started_at=job.get("started_at"),
            finished_at=job.get("finished_at"),
            expires_at=job.get("expires_at"),
            deadline_at=str(job["deadline_at"]),
            queue_position=self.store.queue_position(str(job["job_id"])),
            cancel_requested=bool(job["cancel_requested"]),
            input=InputSummary(
                filename=str(job["filename"]),
                record_count=int(job["record_count"]),
                sequence_count=int(job["record_count"]),
                total_sequence_length=int(job["base_count"]),
                sequence_unit="aa" if protein_input else "bp",
                input_kind="protein_fasta" if protein_input else "nucleotide_fasta",
                alphabet="iupac_amino_acid" if protein_input else "iupac_nucleotide",
                base_count=None if protein_input else int(job["base_count"]),
                residue_count=int(job["base_count"]) if protein_input else None,
                sha256=str(job["input_sha256"]),
                source_ids=list(job["source_ids"]),
            ),
            options=JobOptions(
                analysis_mode=analysis_mode,
                include_crispr_arrays=bool(job.get("include_crispr_arrays")),
                gene_mode=(None if protein_input else GeneMode(effective_gene_mode)),
                translation_table=None if protein_input else 11,
                translation_table_scope=(None if protein_input else "single_mode_training_request"),
            ),
            summary=job.get("summary"),
            artifacts=artifacts,
            error=error,
        )

    @staticmethod
    def _write_input(
        root: Path,
        normalized: NormalizedFasta,
        *,
        input_filename: str,
        write_records: bool,
    ) -> None:
        root.mkdir(mode=0o700, parents=False, exist_ok=False)
        input_root = root / "input"
        output_root = root / "output"
        input_root.mkdir(mode=0o700)
        output_root.mkdir(mode=0o700)
        combined = input_root / input_filename
        combined.write_bytes(normalized.data)
        os.chmod(combined, 0o600)
        if not write_records:
            return
        records_root = input_root / "records"
        records_root.mkdir(mode=0o700)
        for index, record in enumerate(normalized.records, start=1):
            suffix = ".faa" if input_filename.endswith(".faa") else ".fasta"
            path = records_root / f"record-{index:04d}{suffix}"
            rendered = (
                f">{record.source_id}\n"
                + "\n".join(
                    record.sequence[offset : offset + 80]
                    for offset in range(0, len(record.sequence), 80)
                )
                + "\n"
            ).encode("ascii")
            path.write_bytes(rendered)
            os.chmod(path, 0o600)

    def _remove_job_tree(self, root: Path) -> None:
        try:
            root.resolve(strict=False).relative_to(self.jobs_root.resolve())
        except ValueError as error:
            raise RuntimeError("refusing to remove a path outside the jobs root") from error
        if root.name and _JOB_ID.fullmatch(root.name) and root.exists():
            shutil.rmtree(root)

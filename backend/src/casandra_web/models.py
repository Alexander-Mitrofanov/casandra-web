"""Typed public API models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GeneMode(str, Enum):
    auto = "auto"
    meta = "meta"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobPhase(str, Enum):
    queued = "queued"
    casandra = "casandra"
    crispridentify = "crispridentify"
    indexing = "indexing"
    packaging = "packaging"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: str = Field(min_length=1, description="Plain IUPAC nucleotide FASTA or DNA")
    filename: str | None = Field(default=None, max_length=255)
    gene_mode: GeneMode = GeneMode.auto


class InputSummary(BaseModel):
    filename: str
    record_count: int
    base_count: int
    sha256: str
    source_ids: list[str]


class JobOptions(BaseModel):
    gene_mode: GeneMode
    translation_table: Literal[11] = 11
    translation_table_scope: Literal["single_mode_training_request"] = (
        "single_mode_training_request"
    )


class ArtifactView(BaseModel):
    artifact_id: str
    name: str
    size_bytes: int
    sha256: str
    media_type: str
    download_url: str


class ErrorView(BaseModel):
    code: str
    message: str


class JobView(BaseModel):
    job_id: str
    status: JobStatus
    phase: JobPhase
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    expires_at: str | None = None
    deadline_at: str
    queue_position: int | None = None
    cancel_requested: bool = False
    input: InputSummary
    options: JobOptions
    summary: dict[str, Any] | None = None
    artifacts: list[ArtifactView] = Field(default_factory=list)
    error: ErrorView | None = None


class JobCreated(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    job: JobView


class CancelResponse(BaseModel):
    job: JobView


class PublicConfig(BaseModel):
    service: str
    api_version: str
    gene_modes: list[GeneMode]
    translation_table: Literal[11] = 11
    translation_table_scope: Literal["single_mode_training_request"] = (
        "single_mode_training_request"
    )
    max_request_bytes: int
    max_total_bases: int
    max_record_bases: int
    max_records: int
    max_header_characters: int
    max_queued_jobs: int
    max_active_jobs: int
    max_active_jobs_per_client: int
    retention_seconds: int
    max_retained_jobs: int
    submission_window_seconds: int
    max_submissions_per_window: int
    max_job_lifetime_seconds: int
    casandra_is_authoritative: Literal[True] = True
    array_overlay_changes_cas_calls: Literal[False] = False


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]
    worker: Literal["ok", "stale", "not_started", "error"]
    service: str
    version: str


class VersionResponse(BaseModel):
    service: str
    version: str
    api_version: str
    casandra_role: Literal["authoritative_cas_caller"]
    crispridentify_role: Literal["independent_array_overlay"]

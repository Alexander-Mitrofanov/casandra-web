"""Typed public API models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnalysisMode(str, Enum):
    complete_genome = "complete_genome"
    annotate_cas_genes = "annotate_cas_genes"
    classify_cassette = "classify_cassette"
    metagenomic = "metagenomic"


class GeneMode(str, Enum):
    auto = "auto"
    single = "single"
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

    analysis_mode: AnalysisMode = AnalysisMode.complete_genome
    sequence: str = Field(
        min_length=1,
        description="Nucleotide FASTA for genome modes or amino-acid FASTA for protein modes",
    )
    filename: str | None = Field(default=None, max_length=255)
    include_crispr_arrays: bool = Field(
        default=False,
        strict=True,
        description="Complement complete-genome analysis with CRISPR array detection",
    )
    gene_mode: GeneMode | None = None

    @model_validator(mode="before")
    @classmethod
    def translate_legacy_gene_mode(cls, value: object) -> object:
        """Map the old gene-mode-only request onto an unambiguous analysis mode."""

        if not isinstance(value, dict):
            return value
        if "analysis_mode" in value:
            if (
                value.get("analysis_mode")
                in {
                    AnalysisMode.complete_genome,
                    AnalysisMode.complete_genome.value,
                }
                and value.get("gene_mode") is not None
            ):
                raise ValueError(
                    "gene_mode is legacy-only; complete_genome uses single gene calling"
                )
            return value
        translated = dict(value)
        # Before analysis_mode existed every request was a complete-genome run,
        # optionally forcing Pyrodigal meta mode, and always included arrays.
        translated["analysis_mode"] = AnalysisMode.complete_genome
        translated.setdefault("include_crispr_arrays", True)
        translated.setdefault("gene_mode", GeneMode.auto)
        return translated

    @model_validator(mode="after")
    def validate_mode_options(self) -> JobSubmission:
        if self.analysis_mode == AnalysisMode.complete_genome:
            if self.gene_mode is None:
                self.gene_mode = GeneMode.single
        elif self.analysis_mode == AnalysisMode.metagenomic:
            if self.gene_mode not in {None, GeneMode.meta}:
                raise ValueError("metagenomic analysis uses metagenomic gene calling")
            if self.include_crispr_arrays:
                raise ValueError("CRISPR array detection is available only for complete_genome")
            self.gene_mode = GeneMode.meta
        else:
            if self.gene_mode is not None:
                raise ValueError("gene_mode is not accepted for protein analysis modes")
            if self.include_crispr_arrays:
                raise ValueError("CRISPR array detection is available only for complete_genome")
        return self


class InputSummary(BaseModel):
    filename: str
    record_count: int
    sequence_count: int
    total_sequence_length: int
    sequence_unit: Literal["bp", "aa"]
    input_kind: Literal["nucleotide_fasta", "protein_fasta"]
    alphabet: Literal["iupac_nucleotide", "iupac_amino_acid"]
    base_count: int | None = None
    residue_count: int | None = None
    sha256: str
    source_ids: list[str]


class JobOptions(BaseModel):
    analysis_mode: AnalysisMode
    include_crispr_arrays: bool
    gene_mode: GeneMode | None
    translation_table: Literal[11] | None = 11
    translation_table_scope: Literal["single_mode_training_request"] | None = (
        "single_mode_training_request"
    )


class ArtifactView(BaseModel):
    artifact_id: str
    name: str
    size_bytes: int
    sha256: str
    media_type: str
    download_url: str
    role: Literal["results", "sequences", "bundle", "technical"] = "technical"
    format: Literal["json", "csv", "fasta", "tsv", "gff3", "zip", "other"] = "other"
    scope: str | None = None
    molecule: Literal["protein", "dna"] | None = None
    authoritative: Literal[True] = True


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


class InputPolicyCondition(BaseModel):
    include_crispr_arrays: bool


class NucleotideInputPolicy(BaseModel):
    when: InputPolicyCondition
    max_request_bytes: int
    max_total_bases: int
    max_record_bases: int
    max_records: int


class InputPolicies(BaseModel):
    cas_only: NucleotideInputPolicy
    with_crispr_arrays: NucleotideInputPolicy


class PublicConfig(BaseModel):
    service: str
    api_version: str
    analysis_modes: list[AnalysisMode]
    gene_modes: list[GeneMode]
    translation_table: Literal[11] = 11
    translation_table_scope: Literal["single_mode_training_request"] = (
        "single_mode_training_request"
    )
    max_request_bytes: int
    max_total_bases: int
    max_record_bases: int
    max_cas_only_request_bytes: int
    max_cas_only_total_bases: int
    max_cas_only_record_bases: int
    max_cas_only_records: int
    max_array_request_bytes: int
    max_array_total_bases: int
    max_array_record_bases: int
    max_array_records: int
    input_policies: InputPolicies
    max_protein_request_bytes: int
    max_total_residues: int
    max_record_residues: int
    max_protein_residues: int
    max_protein_records: int
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


class CasandraModelIdentity(BaseModel):
    bundle_id: str
    bundle_manifest_sha256: str
    program_version: str
    schema_version: int
    bundle_role: str


class VersionResponse(BaseModel):
    service: str
    version: str
    api_version: str
    web_release_id: str | None
    casandra_role: Literal["authoritative_cas_caller"]
    crispridentify_role: Literal["independent_array_overlay"]
    casandra_bundle_id: str | None = None
    casandra_bundle_manifest_sha256: str | None = None
    casandra_program_version: str | None = None
    casandra_schema_version: int | None = None
    casandra_bundle_role: str | None = None
    casandra_model: CasandraModelIdentity | None = None

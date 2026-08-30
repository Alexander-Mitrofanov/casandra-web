"""Strict operator-owned service configuration."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = default if raw is None else int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _path(name: str, default: str) -> Path:
    value = Path(os.getenv(name, default)).expanduser().resolve()
    if value == Path(value.anchor):
        raise ValueError(f"{name} cannot be a filesystem root")
    return value


def _command(name: str, default: list[str]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        value: object = default
    else:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(f"{name} must be a JSON string array") from error
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item and "\0" not in item for item in value)
    ):
        raise ValueError(f"{name} must be a non-empty JSON string array")
    return tuple(value)


def _origins(raw: str) -> tuple[str, ...]:
    origins: list[str] = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError(f"invalid exact CORS origin: {value!r}")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("HTTP CORS origins are allowed only for loopback development")
        if "*" in value:
            raise ValueError("CORS origins cannot contain wildcards")
        origins.append(value.rstrip("/"))
    if len(origins) != len(set(origins)):
        raise ValueError("CORS origins contain duplicates")
    return tuple(origins)


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


_PUBLIC_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _public_scientific_identity() -> tuple[str | None, str | None, str | None, int | None, str | None]:
    """Read an all-or-none, non-secret scientific identity attestation."""

    names = (
        "CASANDRA_WEB_CASANDRA_BUNDLE_ID",
        "CASANDRA_WEB_CASANDRA_BUNDLE_MANIFEST_SHA256",
        "CASANDRA_WEB_CASANDRA_PROGRAM_VERSION",
        "CASANDRA_WEB_CASANDRA_SCHEMA_VERSION",
        "CASANDRA_WEB_CASANDRA_BUNDLE_ROLE",
    )
    raw = tuple(os.getenv(name) for name in names)
    if not any(value is not None for value in raw):
        return None, None, None, None, None
    if any(value is None or not value for value in raw):
        raise ValueError("CasAndra public scientific identity must be configured all-or-none")
    bundle_id, manifest_sha256, program_version, schema_raw, bundle_role = raw
    assert all(value is not None for value in raw)
    if _PUBLIC_IDENTITY.fullmatch(bundle_id) is None:
        raise ValueError("CASANDRA_WEB_CASANDRA_BUNDLE_ID is invalid")
    if _SHA256.fullmatch(manifest_sha256) is None:
        raise ValueError("CASANDRA_WEB_CASANDRA_BUNDLE_MANIFEST_SHA256 must be lowercase SHA-256")
    if _PUBLIC_IDENTITY.fullmatch(program_version) is None:
        raise ValueError("CASANDRA_WEB_CASANDRA_PROGRAM_VERSION is invalid")
    if _PUBLIC_IDENTITY.fullmatch(bundle_role) is None:
        raise ValueError("CASANDRA_WEB_CASANDRA_BUNDLE_ROLE is invalid")
    try:
        schema_version = int(schema_raw)
    except ValueError as error:
        raise ValueError("CASANDRA_WEB_CASANDRA_SCHEMA_VERSION must be an integer") from error
    if not 1 <= schema_version <= 1_000:
        raise ValueError("CASANDRA_WEB_CASANDRA_SCHEMA_VERSION must be between 1 and 1000")
    expected_version = os.getenv("CASANDRA_WEB_CASANDRA_EXPECTED_VERSION")
    if expected_version is not None and expected_version != f"casandra {program_version}":
        raise ValueError("public CasAndra program version does not match the runtime pin")
    return bundle_id, manifest_sha256, program_version, schema_version, bundle_role


@dataclass(frozen=True, slots=True)
class Settings:
    data_root: Path
    database_path: Path
    token_pepper: str
    cors_origins: tuple[str, ...]
    casandra_command: tuple[str, ...]
    identify_command: tuple[str, ...]
    identify_runner_config: Path | None
    max_request_bytes: int = 10_000_000
    max_total_bases: int = 8_000_000
    max_record_bases: int = 8_000_000
    max_records: int = 100
    max_array_request_bytes: int = 4_500_000
    max_array_total_bases: int = 2_000_000
    max_array_records: int = 20
    max_protein_request_bytes: int = 4_500_000
    max_total_residues: int = 2_000_000
    max_protein_residues: int = 100_000
    max_protein_records: int = 10_000
    max_header_characters: int = 240
    max_queued_jobs: int = 8
    max_active_jobs: int = 9
    max_active_jobs_per_client: int = 2
    retention_seconds: int = 259_200
    worker_cpu: int = 4
    stage_timeout_seconds: int = 1_800
    worker_poll_seconds: int = 2
    worker_heartbeat_seconds: int = 15
    worker_stale_seconds: int = 90
    max_attempts: int = 2
    max_log_bytes: int = 2_000_000
    max_retained_jobs: int = 20
    max_retained_input_bases: int = 20_000_000
    submission_window_seconds: int = 3_600
    max_submissions_per_window: int = 3
    min_free_bytes: int = 5_000_000_000
    min_free_inodes: int = 100_000
    max_job_storage_bytes: int = 600_000_000
    max_job_lifetime_seconds: int = 28_800
    service_name: str = "CasAndra Web"
    api_version: str = "1.1.0"
    preflight_scientific_runtime: bool = False
    casandra_expected_version: str | None = None
    integration_expected_version: str | None = None
    crispridentify_version_file: Path | None = None
    crispridentify_expected_version: str | None = None
    casandra_bundle_id: str | None = None
    casandra_bundle_manifest_sha256: str | None = None
    casandra_program_version: str | None = None
    casandra_schema_version: int | None = None
    casandra_bundle_role: str | None = None

    def __post_init__(self) -> None:
        identity = (
            self.casandra_bundle_id,
            self.casandra_bundle_manifest_sha256,
            self.casandra_program_version,
            self.casandra_schema_version,
            self.casandra_bundle_role,
        )
        if any(value is not None for value in identity) and not all(
            value is not None for value in identity
        ):
            raise ValueError("CasAndra public scientific identity must be configured all-or-none")
        largest_input = max(self.max_total_bases, self.max_total_residues)
        if self.max_retained_input_bases < largest_input:
            raise ValueError(
                "max_retained_input_bases must admit at least one maximum-sized input"
            )
        if self.max_active_jobs < self.max_queued_jobs + 1:
            raise ValueError("max_active_jobs must allow every queued job plus one running job")
        if self.max_active_jobs_per_client > self.max_active_jobs:
            raise ValueError("max_active_jobs_per_client cannot exceed max_active_jobs")
        if self.max_retained_jobs < self.max_active_jobs:
            raise ValueError("max_retained_jobs cannot be lower than max_active_jobs")

    @classmethod
    def from_env(cls) -> Settings:
        data_root = _path("CASANDRA_WEB_DATA_ROOT", "/tmp/casandra-web")
        database_path = _path("CASANDRA_WEB_DATABASE_PATH", str(data_root / "queue.sqlite3"))
        pepper = os.getenv("CASANDRA_WEB_TOKEN_PEPPER", "")
        if not pepper:
            # A deterministic development value is intentionally opt-in only on /tmp.
            if data_root.is_relative_to(Path("/tmp")):
                pepper = "development-only-change-me"
            else:
                raise ValueError("CASANDRA_WEB_TOKEN_PEPPER is required outside /tmp")
        runner_raw = os.getenv("CASANDRA_WEB_IDENTIFY_RUNNER_CONFIG")
        scientific_identity = _public_scientific_identity()
        return cls(
            data_root=data_root,
            database_path=database_path,
            token_pepper=pepper,
            cors_origins=_origins(
                os.getenv(
                    "CASANDRA_WEB_CORS_ORIGINS",
                    "http://127.0.0.1:4173,http://localhost:4173",
                )
            ),
            casandra_command=_command("CASANDRA_WEB_CASANDRA_COMMAND", ["casandra"]),
            identify_command=_command("CASANDRA_WEB_IDENTIFY_COMMAND", ["crispr-tools"]),
            identify_runner_config=(
                Path(runner_raw).expanduser().resolve() if runner_raw else None
            ),
            max_request_bytes=_integer(
                "CASANDRA_WEB_MAX_REQUEST_BYTES", 10_000_000, 1_024, 110_000_000
            ),
            max_total_bases=_integer(
                "CASANDRA_WEB_MAX_TOTAL_BASES", 8_000_000, 1_000, 100_000_000
            ),
            max_record_bases=_integer(
                "CASANDRA_WEB_MAX_RECORD_BASES", 8_000_000, 1_000, 100_000_000
            ),
            max_records=_integer("CASANDRA_WEB_MAX_RECORDS", 100, 1, 10_000),
            max_array_request_bytes=_integer(
                "CASANDRA_WEB_MAX_ARRAY_REQUEST_BYTES", 4_500_000, 1_024, 110_000_000
            ),
            max_array_total_bases=_integer(
                "CASANDRA_WEB_MAX_ARRAY_TOTAL_BASES", 2_000_000, 1_000, 100_000_000
            ),
            max_array_records=_integer("CASANDRA_WEB_MAX_ARRAY_RECORDS", 20, 1, 10_000),
            max_protein_request_bytes=_integer(
                "CASANDRA_WEB_MAX_PROTEIN_REQUEST_BYTES", 4_500_000, 1_024, 110_000_000
            ),
            max_total_residues=_integer(
                "CASANDRA_WEB_MAX_TOTAL_RESIDUES", 2_000_000, 1_000, 100_000_000
            ),
            max_protein_residues=_integer(
                "CASANDRA_WEB_MAX_PROTEIN_RESIDUES", 100_000, 100, 10_000_000
            ),
            max_protein_records=_integer(
                "CASANDRA_WEB_MAX_PROTEIN_RECORDS", 10_000, 1, 100_000
            ),
            max_header_characters=_integer("CASANDRA_WEB_MAX_HEADER_CHARACTERS", 240, 16, 2_000),
            max_queued_jobs=_integer("CASANDRA_WEB_MAX_QUEUED_JOBS", 8, 1, 1_000),
            max_active_jobs=_integer("CASANDRA_WEB_MAX_ACTIVE_JOBS", 9, 1, 1_001),
            max_active_jobs_per_client=_integer("CASANDRA_WEB_MAX_ACTIVE_PER_CLIENT", 2, 1, 100),
            retention_seconds=_integer("CASANDRA_WEB_RETENTION_SECONDS", 259_200, 300, 2_592_000),
            worker_cpu=_integer("CASANDRA_WEB_WORKER_CPU", 4, 1, 16),
            stage_timeout_seconds=_integer("CASANDRA_WEB_STAGE_TIMEOUT_SECONDS", 1_800, 10, 86_400),
            worker_poll_seconds=_integer("CASANDRA_WEB_WORKER_POLL_SECONDS", 2, 1, 60),
            worker_heartbeat_seconds=_integer("CASANDRA_WEB_HEARTBEAT_SECONDS", 15, 2, 300),
            worker_stale_seconds=_integer("CASANDRA_WEB_WORKER_STALE_SECONDS", 90, 10, 3_600),
            max_attempts=_integer("CASANDRA_WEB_MAX_ATTEMPTS", 2, 1, 5),
            max_log_bytes=_integer("CASANDRA_WEB_MAX_LOG_BYTES", 2_000_000, 1_024, 100_000_000),
            max_retained_jobs=_integer("CASANDRA_WEB_MAX_RETAINED_JOBS", 20, 1, 10_000),
            max_retained_input_bases=_integer(
                "CASANDRA_WEB_MAX_RETAINED_INPUT_BASES",
                20_000_000,
                1_000,
                1_000_000_000,
            ),
            submission_window_seconds=_integer(
                "CASANDRA_WEB_SUBMISSION_WINDOW_SECONDS", 3_600, 60, 86_400
            ),
            max_submissions_per_window=_integer(
                "CASANDRA_WEB_MAX_SUBMISSIONS_PER_WINDOW", 3, 1, 1_000
            ),
            min_free_bytes=_integer(
                "CASANDRA_WEB_MIN_FREE_BYTES", 5_000_000_000, 10_000_000, 1_000_000_000_000
            ),
            min_free_inodes=_integer(
                "CASANDRA_WEB_MIN_FREE_INODES", 100_000, 1_000, 1_000_000_000
            ),
            max_job_storage_bytes=_integer(
                "CASANDRA_WEB_MAX_JOB_STORAGE_BYTES",
                600_000_000,
                10_000_000,
                20_000_000_000,
            ),
            max_job_lifetime_seconds=_integer(
                "CASANDRA_WEB_MAX_JOB_LIFETIME_SECONDS", 28_800, 600, 604_800
            ),
            preflight_scientific_runtime=_boolean(
                "CASANDRA_WEB_PREFLIGHT_SCIENTIFIC_RUNTIME", False
            ),
            casandra_expected_version=os.getenv("CASANDRA_WEB_CASANDRA_EXPECTED_VERSION"),
            integration_expected_version=os.getenv("CASANDRA_WEB_INTEGRATION_EXPECTED_VERSION"),
            crispridentify_version_file=(
                Path(value).expanduser().resolve()
                if (value := os.getenv("CASANDRA_WEB_CRISPRIDENTIFY_VERSION_FILE"))
                else None
            ),
            crispridentify_expected_version=os.getenv(
                "CASANDRA_WEB_CRISPRIDENTIFY_EXPECTED_VERSION"
            ),
            casandra_bundle_id=scientific_identity[0],
            casandra_bundle_manifest_sha256=scientific_identity[1],
            casandra_program_version=scientific_identity[2],
            casandra_schema_version=scientific_identity[3],
            casandra_bundle_role=scientific_identity[4],
        )

    @property
    def effective_array_request_bytes(self) -> int:
        return min(self.max_request_bytes, self.max_array_request_bytes)

    @property
    def effective_record_bases(self) -> int:
        return min(self.max_record_bases, self.max_total_bases)

    @property
    def effective_array_total_bases(self) -> int:
        return min(self.max_total_bases, self.max_array_total_bases)

    @property
    def effective_array_records(self) -> int:
        return min(self.max_records, self.max_array_records)

    @property
    def effective_array_record_bases(self) -> int:
        return min(self.effective_record_bases, self.effective_array_total_bases)

    @property
    def effective_protein_request_bytes(self) -> int:
        return min(self.max_request_bytes, self.max_protein_request_bytes)

    @property
    def effective_protein_record_residues(self) -> int:
        return min(self.max_protein_residues, self.max_total_residues)

    def prepare(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.data_root, 0o700)
        self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

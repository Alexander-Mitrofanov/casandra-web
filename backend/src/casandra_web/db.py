"""SQLite WAL queue and job metadata store."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import Settings


class CapacityError(RuntimeError):
    pass


class StorageCapacityError(RuntimeError):
    pass


class LeaseError(RuntimeError):
    pass


class CancellationPending(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def expiry_time(retention_seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=retention_seconds)).isoformat()


def deadline_time(lifetime_seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=lifetime_seconds)).isoformat()


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    job_id: str
    worker_id: str
    attempt: int
    gene_mode: str
    analysis_mode: str = "complete_genome"
    include_crispr_arrays: bool = False


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = Path(settings.database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def initialize(self) -> None:
        self.settings.prepare()
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    token_digest TEXT NOT NULL,
                    client_digest TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed','cancelled')),
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
                    gene_mode TEXT NOT NULL CHECK(gene_mode IN ('auto','single','meta')),
                    requested_gene_mode TEXT,
                    analysis_mode TEXT NOT NULL DEFAULT 'complete_genome',
                    include_crispr_arrays INTEGER NOT NULL DEFAULT 0,
                    summary_json TEXT,
                    error_code TEXT,
                    error_message TEXT
                );
                CREATE INDEX IF NOT EXISTS jobs_queue_idx ON jobs(status, created_at);
                CREATE INDEX IF NOT EXISTS jobs_client_idx ON jobs(client_digest, status);
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    UNIQUE(job_id, name)
                );
                CREATE TABLE IF NOT EXISTS workers (
                    worker_id TEXT PRIMARY KEY,
                    heartbeat_at REAL NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS submission_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_digest TEXT NOT NULL,
                    submitted_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS submission_events_client_idx
                    ON submission_events(client_digest, submitted_at);
                CREATE INDEX IF NOT EXISTS submission_events_time_idx
                    ON submission_events(submitted_at);
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
            }
            if "deadline_at" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN deadline_at TEXT")
                connection.execute(
                    "UPDATE jobs SET deadline_at=COALESCE(expires_at, ?)",
                    (deadline_time(self.settings.max_job_lifetime_seconds),),
                )
            legacy_mode_schema = "analysis_mode" not in columns
            if legacy_mode_schema:
                connection.execute(
                    "ALTER TABLE jobs ADD COLUMN analysis_mode TEXT NOT NULL "
                    "DEFAULT 'complete_genome'"
                )
            if "include_crispr_arrays" not in columns:
                connection.execute(
                    "ALTER TABLE jobs ADD COLUMN include_crispr_arrays INTEGER NOT NULL DEFAULT 0"
                )
                if legacy_mode_schema:
                    # Jobs admitted by the v1 API always ran the independent array overlay.
                    connection.execute("UPDATE jobs SET include_crispr_arrays=1")
            if "requested_gene_mode" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN requested_gene_mode TEXT")

    def _ensure_storage_capacity(self) -> None:
        usage = shutil.disk_usage(self.settings.data_root)
        if usage.free < self.settings.min_free_bytes:
            raise StorageCapacityError("The analysis service is low on free storage")
        filesystem = os.statvfs(self.settings.data_root)
        if filesystem.f_favail < self.settings.min_free_inodes:
            raise StorageCapacityError("The analysis service is low on free filesystem entries")

    def _check_admission(
        self,
        connection: sqlite3.Connection,
        *,
        client_digest: str,
        base_count: int,
        record_event: bool,
    ) -> None:
        cutoff = time.time() - self.settings.submission_window_seconds
        connection.execute("DELETE FROM submission_events WHERE submitted_at < ?", (cutoff,))
        recent = connection.execute(
            "SELECT COUNT(*) FROM submission_events WHERE client_digest=? AND submitted_at>=?",
            (client_digest, cutoff),
        ).fetchone()[0]
        if recent >= self.settings.max_submissions_per_window:
            raise CapacityError("This client has reached the recent submission limit")
        retained = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        if retained >= self.settings.max_retained_jobs:
            raise StorageCapacityError("The analysis service has reached its retained-job limit")
        retained_bases = connection.execute(
            "SELECT COALESCE(SUM(base_count), 0) FROM jobs"
        ).fetchone()[0]
        if retained_bases + base_count > self.settings.max_retained_input_bases:
            raise StorageCapacityError("The analysis service has reached its retained-input limit")
        queued = connection.execute("SELECT COUNT(*) FROM jobs WHERE status='queued'").fetchone()[0]
        if queued >= self.settings.max_queued_jobs:
            raise CapacityError("The analysis queue is currently full")
        active = connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')"
        ).fetchone()[0]
        if active >= self.settings.max_active_jobs:
            raise CapacityError("The analysis service has reached its active-job limit")
        client_active = connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE client_digest=? AND status IN ('queued','running')",
            (client_digest,),
        ).fetchone()[0]
        if client_active >= self.settings.max_active_jobs_per_client:
            raise CapacityError("This client already has the maximum number of active jobs")
        if record_event:
            connection.execute(
                "INSERT INTO submission_events(client_digest, submitted_at) VALUES (?, ?)",
                (client_digest, time.time()),
            )

    def check_admission(self, client_digest: str, base_count: int) -> None:
        self._ensure_storage_capacity()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._check_admission(
                    connection,
                    client_digest=client_digest,
                    base_count=base_count,
                    record_event=False,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def ping(self) -> bool:
        try:
            with self._connect() as connection:
                return connection.execute("SELECT 1").fetchone()[0] == 1
        except sqlite3.Error:
            return False

    def create_job(
        self,
        *,
        job_id: str,
        token_digest: str,
        client_digest: str,
        filename: str,
        record_count: int,
        base_count: int,
        input_sha256: str,
        source_ids: Iterable[str],
        gene_mode: str,
        analysis_mode: str,
        include_crispr_arrays: bool,
    ) -> dict[str, Any]:
        now = utc_now()
        deadline = deadline_time(self.settings.max_job_lifetime_seconds)
        self._ensure_storage_capacity()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._check_admission(
                    connection,
                    client_digest=client_digest,
                    base_count=base_count,
                    record_event=True,
                )
                connection.execute(
                    """
                    INSERT INTO jobs (
                        job_id, token_digest, client_digest, status, phase,
                        created_at, updated_at, deadline_at, max_attempts, filename,
                        record_count, base_count, input_sha256, source_ids_json, gene_mode,
                        analysis_mode, include_crispr_arrays, requested_gene_mode
                    ) VALUES (?, ?, ?, 'queued', 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        token_digest,
                        client_digest,
                        now,
                        now,
                        deadline,
                        self.settings.max_attempts,
                        filename,
                        record_count,
                        base_count,
                        input_sha256,
                        json.dumps(list(source_ids), separators=(",", ":")),
                        gene_mode if gene_mode in {"auto", "meta"} else "auto",
                        analysis_mode,
                        int(include_crispr_arrays),
                        gene_mode,
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return self.get_job(job_id) or {}

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._job_dict(row) if row is not None else None

    def queue_position(self, job_id: str) -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT created_at, status FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None or row["status"] != "queued":
                return None
            ahead = connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='queued' AND (created_at < ? OR (created_at = ? AND job_id < ?))",
                (row["created_at"], row["created_at"], job_id),
            ).fetchone()[0]
        return int(ahead) + 1

    def list_artifacts(self, job_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM artifacts WHERE job_id=? ORDER BY name", (job_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_artifact(self, job_id: str, artifact_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM artifacts WHERE job_id=? AND artifact_id=?",
                (job_id, artifact_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def heartbeat_worker(self, worker_id: str, status: str = "ok") -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workers(worker_id, heartbeat_at, status) VALUES (?, ?, ?)
                ON CONFLICT(worker_id) DO UPDATE SET heartbeat_at=excluded.heartbeat_at, status=excluded.status
                """,
                (worker_id, time.time(), status),
            )

    def worker_state(self) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT heartbeat_at, status FROM workers ORDER BY heartbeat_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return "not_started"
        if row["status"] != "ok":
            return "error"
        return (
            "ok"
            if time.time() - float(row["heartbeat_at"]) <= self.settings.worker_stale_seconds
            else "stale"
        )

    def claim_next(self, worker_id: str) -> ClaimedJob | None:
        now_epoch = time.time()
        now = utc_now()
        expires = expiry_time(self.settings.retention_seconds)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    UPDATE jobs SET status='failed', phase='failed', finished_at=?, updated_at=?,
                        expires_at=?, error_code='job_deadline_exceeded',
                        error_message='The job exceeded its absolute queue and runtime deadline.'
                    WHERE status='queued' AND deadline_at <= ?
                    """,
                    (now, now, expires, now),
                )
                connection.execute(
                    """
                    UPDATE jobs SET cancel_requested=1, updated_at=?
                    WHERE status='running' AND deadline_at <= ?
                    """,
                    (now, now),
                )
                connection.execute(
                    """
                    UPDATE jobs SET status='cancelled', phase='cancelled', finished_at=?, updated_at=?,
                        expires_at=?, worker_id=NULL, lease_expires=NULL
                    WHERE status='running' AND lease_expires < ? AND cancel_requested=1
                    """,
                    (now, now, expires, now_epoch),
                )
                connection.execute(
                    """
                    UPDATE jobs SET status='queued', phase='queued', worker_id=NULL, lease_expires=NULL, updated_at=?
                    WHERE status='running' AND lease_expires < ? AND cancel_requested=0 AND attempt < max_attempts
                    """,
                    (now, now_epoch),
                )
                connection.execute(
                    """
                    UPDATE jobs SET status='failed', phase='failed', finished_at=?, updated_at=?,
                        expires_at=?, error_code='worker_lost',
                        error_message='The scientific worker stopped before the job completed.',
                        worker_id=NULL, lease_expires=NULL
                    WHERE status='running' AND lease_expires < ? AND cancel_requested=0 AND attempt >= max_attempts
                    """,
                    (now, now, expires, now_epoch),
                )
                row = connection.execute(
                    "SELECT job_id, attempt, COALESCE(requested_gene_mode, gene_mode) "
                    "AS execution_gene_mode, analysis_mode, include_crispr_arrays "
                    "FROM jobs WHERE status='queued' AND cancel_requested=0 "
                    "ORDER BY created_at, job_id LIMIT 1"
                ).fetchone()
                if row is None:
                    connection.commit()
                    return None
                attempt = int(row["attempt"]) + 1
                connection.execute(
                    """
                    UPDATE jobs SET status='running', phase='casandra', worker_id=?, attempt=?,
                        started_at=COALESCE(started_at, ?), updated_at=?, lease_expires=?
                    WHERE job_id=? AND status='queued'
                    """,
                    (
                        worker_id,
                        attempt,
                        now,
                        now,
                        now_epoch + self.settings.worker_stale_seconds,
                        row["job_id"],
                    ),
                )
                connection.commit()
                return ClaimedJob(
                    str(row["job_id"]),
                    worker_id,
                    attempt,
                    str(row["execution_gene_mode"]),
                    str(row["analysis_mode"]),
                    bool(row["include_crispr_arrays"]),
                )
            except Exception:
                connection.rollback()
                raise

    def renew_lease(self, claimed: ClaimedJob) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET lease_expires=?, updated_at=?
                WHERE job_id=? AND status='running' AND worker_id=? AND attempt=?
                """,
                (
                    time.time() + self.settings.worker_stale_seconds,
                    utc_now(),
                    claimed.job_id,
                    claimed.worker_id,
                    claimed.attempt,
                ),
            )
        if cursor.rowcount != 1:
            raise LeaseError("job lease is no longer owned by this worker")

    def set_phase(self, claimed: ClaimedJob, phase: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET phase=?, updated_at=?
                WHERE job_id=? AND status='running' AND worker_id=? AND attempt=?
                """,
                (phase, utc_now(), claimed.job_id, claimed.worker_id, claimed.attempt),
            )
        if cursor.rowcount != 1:
            raise LeaseError("job lease is no longer owned by this worker")

    def release_after_shutdown(self, claimed: ClaimedJob) -> None:
        """Return a gracefully interrupted job to the queue without publishing output."""

        now = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET status='queued', phase='queued', updated_at=?,
                    worker_id=NULL, lease_expires=NULL, attempt=MAX(attempt - 1, 0)
                WHERE job_id=? AND status='running' AND worker_id=? AND attempt=?
                    AND cancel_requested=0
                """,
                (now, claimed.job_id, claimed.worker_id, claimed.attempt),
            )
        if cursor.rowcount != 1:
            raise LeaseError("job cannot be released for another worker attempt")

    def cancellation_requested(self, claimed: ClaimedJob) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT cancel_requested, deadline_at FROM jobs
                WHERE job_id=? AND status='running' AND worker_id=? AND attempt=?
                """,
                (claimed.job_id, claimed.worker_id, claimed.attempt),
            ).fetchone()
        if row is None:
            raise LeaseError("job lease is no longer owned by this worker")
        return bool(row["cancel_requested"]) or str(row["deadline_at"]) <= utc_now()

    def complete(
        self,
        claimed: ClaimedJob,
        summary: dict[str, Any],
        artifacts: Iterable[dict[str, Any]],
    ) -> None:
        now = utc_now()
        expires = expiry_time(self.settings.retention_seconds)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                owned = connection.execute(
                    """
                    SELECT cancel_requested FROM jobs
                    WHERE job_id=? AND status='running' AND worker_id=? AND attempt=?
                    """,
                    (claimed.job_id, claimed.worker_id, claimed.attempt),
                ).fetchone()
                if owned is None:
                    raise LeaseError("job lease is no longer owned by this worker")
                if bool(owned["cancel_requested"]):
                    raise CancellationPending("job cancellation was requested before completion")
                connection.execute("DELETE FROM artifacts WHERE job_id=?", (claimed.job_id,))
                for artifact in artifacts:
                    connection.execute(
                        """
                        INSERT INTO artifacts (
                            artifact_id, job_id, name, relative_path,
                            size_bytes, sha256, media_type
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            artifact["artifact_id"],
                            claimed.job_id,
                            artifact["name"],
                            artifact["relative_path"],
                            artifact["size_bytes"],
                            artifact["sha256"],
                            artifact["media_type"],
                        ),
                    )
                connection.execute(
                    """
                    UPDATE jobs SET status='completed', phase='completed', summary_json=?,
                        finished_at=?, updated_at=?, expires_at=?,
                        worker_id=NULL, lease_expires=NULL
                    WHERE job_id=? AND status='running' AND worker_id=? AND attempt=?
                        AND cancel_requested=0
                    """,
                    (
                        json.dumps(summary, separators=(",", ":"), allow_nan=False),
                        now,
                        now,
                        expires,
                        claimed.job_id,
                        claimed.worker_id,
                        claimed.attempt,
                    ),
                )
                if connection.execute("SELECT changes()").fetchone()[0] != 1:
                    raise CancellationPending("job cancellation won the completion race")
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def fail(self, claimed: ClaimedJob, code: str, message: str) -> None:
        now = utc_now()
        expires = expiry_time(self.settings.retention_seconds)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs SET status='failed', phase='failed', error_code=?, error_message=?,
                    finished_at=?, updated_at=?, expires_at=?,
                    worker_id=NULL, lease_expires=NULL
                WHERE job_id=? AND status='running' AND worker_id=? AND attempt=?
                """,
                (
                    code[:80],
                    message[:1_000],
                    now,
                    now,
                    expires,
                    claimed.job_id,
                    claimed.worker_id,
                    claimed.attempt,
                ),
            )

    def mark_cancelled(self, claimed: ClaimedJob) -> None:
        now = utc_now()
        expires = expiry_time(self.settings.retention_seconds)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs SET status='cancelled', phase='cancelled', finished_at=?, updated_at=?,
                    expires_at=?, worker_id=NULL, lease_expires=NULL
                WHERE job_id=? AND status='running' AND worker_id=? AND attempt=?
                """,
                (
                    now,
                    now,
                    expires,
                    claimed.job_id,
                    claimed.worker_id,
                    claimed.attempt,
                ),
            )

    def request_cancel(self, job_id: str) -> dict[str, Any] | None:
        now = utc_now()
        expires = expiry_time(self.settings.retention_seconds)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT status FROM jobs WHERE job_id=?", (job_id,)
                ).fetchone()
                if row is None:
                    connection.rollback()
                    return None
                if row["status"] == "queued":
                    connection.execute(
                        """
                        UPDATE jobs SET status='cancelled', phase='cancelled', cancel_requested=1,
                            finished_at=?, updated_at=?, expires_at=?
                        WHERE job_id=?
                        """,
                        (now, now, expires, job_id),
                    )
                elif row["status"] == "running":
                    connection.execute(
                        "UPDATE jobs SET cancel_requested=1, updated_at=? WHERE job_id=?",
                        (now, job_id),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return self.get_job(job_id)

    def expire_overdue_jobs(self) -> None:
        now = utc_now()
        expires = expiry_time(self.settings.retention_seconds)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    UPDATE jobs SET status='failed', phase='failed', finished_at=?, updated_at=?,
                        expires_at=?, error_code='job_deadline_exceeded',
                        error_message='The job exceeded its absolute queue and runtime deadline.'
                    WHERE status='queued' AND deadline_at <= ?
                    """,
                    (now, now, expires, now),
                )
                connection.execute(
                    """
                    UPDATE jobs SET cancel_requested=1, updated_at=?
                    WHERE status='running' AND deadline_at <= ?
                    """,
                    (now, now),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def expired_job_ids(self) -> list[str]:
        now = utc_now()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT job_id FROM jobs WHERE status IN ('completed','failed','cancelled') AND expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            ).fetchall()
        return [str(row["job_id"]) for row in rows]

    def delete_job(self, job_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))

    @staticmethod
    def _job_dict(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["source_ids"] = json.loads(value.pop("source_ids_json"))
        value["summary"] = json.loads(value["summary_json"]) if value.get("summary_json") else None
        return value

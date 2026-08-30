from __future__ import annotations

import sys
from pathlib import Path

import pytest

from casandra_web.config import Settings


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    fake = Path(__file__).with_name("fake_tools.py")
    return Settings(
        data_root=tmp_path / "data",
        database_path=tmp_path / "data" / "queue.sqlite3",
        token_pepper="test-pepper-not-a-secret",
        cors_origins=("https://example.github.io",),
        casandra_command=(sys.executable, str(fake), "casandra"),
        identify_command=(sys.executable, str(fake), "identify"),
        identify_runner_config=None,
        max_request_bytes=100_000,
        max_total_bases=50_000,
        max_record_bases=50_000,
        max_records=10,
        max_queued_jobs=3,
        max_active_jobs_per_client=2,
        retention_seconds=300,
        worker_cpu=1,
        stage_timeout_seconds=30,
        worker_poll_seconds=1,
        worker_heartbeat_seconds=2,
        worker_stale_seconds=10,
        max_attempts=2,
        max_log_bytes=100_000,
        casandra_bundle_id="fake-bundle",
        casandra_bundle_manifest_sha256="a" * 64,
        casandra_program_version="0.3.0.dev0",
        casandra_schema_version=5,
        casandra_bundle_role="deployment_refit",
    )

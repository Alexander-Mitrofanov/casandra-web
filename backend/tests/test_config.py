from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from casandra_web.config import Settings

IDENTITY_ENV = {
    "CASANDRA_WEB_CASANDRA_BUNDLE_ID": (
        "casandra-cas-only-cpu-bundle-v5-type-ii-architecture"
    ),
    "CASANDRA_WEB_CASANDRA_BUNDLE_MANIFEST_SHA256": (
        "89657480e1135aec57f7e2b4a45fe5150f10fbdcbf80bf640e4325f7b921a071"
    ),
    "CASANDRA_WEB_CASANDRA_PROGRAM_VERSION": "0.3.0.dev0",
    "CASANDRA_WEB_CASANDRA_SCHEMA_VERSION": "5",
    "CASANDRA_WEB_CASANDRA_BUNDLE_ROLE": "deployment_refit",
}


def test_public_scientific_identity_is_all_or_none_and_runtime_bound(monkeypatch):
    for name, value in IDENTITY_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("CASANDRA_WEB_CASANDRA_EXPECTED_VERSION", "casandra 0.3.0.dev0")

    settings = Settings.from_env()

    assert settings.casandra_bundle_id == IDENTITY_ENV["CASANDRA_WEB_CASANDRA_BUNDLE_ID"]
    assert (
        settings.casandra_bundle_manifest_sha256
        == IDENTITY_ENV["CASANDRA_WEB_CASANDRA_BUNDLE_MANIFEST_SHA256"]
    )
    assert settings.casandra_program_version == "0.3.0.dev0"
    assert settings.casandra_schema_version == 5
    assert settings.casandra_bundle_role == "deployment_refit"

    monkeypatch.delenv("CASANDRA_WEB_CASANDRA_BUNDLE_ROLE")
    with pytest.raises(ValueError, match="all-or-none"):
        Settings.from_env()


def test_public_scientific_identity_rejects_runtime_version_disagreement(monkeypatch):
    for name, value in IDENTITY_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("CASANDRA_WEB_CASANDRA_EXPECTED_VERSION", "casandra 9.9.9")

    with pytest.raises(ValueError, match="does not match the runtime pin"):
        Settings.from_env()


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {"max_retained_input_bases": 49_999},
            "admit at least one maximum-sized input",
        ),
        (
            {"max_queued_jobs": 3, "max_active_jobs": 3},
            "every queued job plus one running job",
        ),
        (
            {"max_active_jobs": 4, "max_active_jobs_per_client": 5},
            "cannot exceed max_active_jobs",
        ),
        (
            {"max_active_jobs": 9, "max_retained_jobs": 8},
            "cannot be lower than max_active_jobs",
        ),
    ],
)
def test_cross_field_capacity_invariants_fail_fast(settings, updates, message):
    with pytest.raises(ValueError, match=message):
        replace(settings, **updates)


def test_effective_input_limits_never_exceed_parent_envelopes(settings):
    configured = replace(
        settings,
        max_request_bytes=1_000,
        max_total_bases=800,
        max_record_bases=900,
        max_array_request_bytes=2_000,
        max_array_total_bases=2_000,
        max_array_records=20,
        max_protein_request_bytes=2_000,
        max_total_residues=500,
        max_protein_residues=1_000,
    )

    assert configured.effective_record_bases == 800
    assert configured.effective_array_request_bytes == 1_000
    assert configured.effective_array_total_bases == 800
    assert configured.effective_array_record_bases == 800
    assert configured.effective_array_records == settings.max_records
    assert configured.effective_protein_request_bytes == 1_000
    assert configured.effective_protein_record_residues == 500


def test_checked_in_standalone_policy_is_exact_and_consistent():
    root = Path(__file__).resolve().parents[2]
    values = {}
    for line in (root / "deploy/casandra-web.env.example").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value

    assert values["CASANDRA_WEB_MAX_REQUEST_BYTES"] == "110000000"
    assert values["CASANDRA_WEB_MAX_TOTAL_BASES"] == "100000000"
    assert values["CASANDRA_WEB_MAX_RECORD_BASES"] == "100000000"
    assert values["CASANDRA_WEB_MAX_RECORDS"] == "10000"
    assert values["CASANDRA_WEB_MAX_ARRAY_REQUEST_BYTES"] == "4500000"
    assert values["CASANDRA_WEB_MAX_ARRAY_TOTAL_BASES"] == "2000000"
    assert values["CASANDRA_WEB_MAX_ARRAY_RECORDS"] == "20"
    assert values["CASANDRA_WEB_MAX_PROTEIN_REQUEST_BYTES"] == "4500000"
    assert values["CASANDRA_WEB_MAX_RETAINED_INPUT_BASES"] == "250000000"
    assert values["CASANDRA_WEB_MIN_FREE_BYTES"] == "20000000000"
    assert values["CASANDRA_WEB_MAX_JOB_STORAGE_BYTES"] == "2000000000"
    assert values["CASANDRA_WEB_MAX_QUEUED_JOBS"] == "1"
    assert values["CASANDRA_WEB_MAX_ACTIVE_JOBS"] == "2"
    assert values["CASANDRA_WEB_MAX_ACTIVE_PER_CLIENT"] == "1"
    assert values["CASANDRA_WEB_WORKER_CPU"] == "3"
    assert values["CASANDRA_WEB_STAGE_TIMEOUT_SECONDS"] == "7200"
    assert values["CASANDRA_WEB_CASANDRA_BUNDLE_MANIFEST_SHA256"] == (
        "89657480e1135aec57f7e2b4a45fe5150f10fbdcbf80bf640e4325f7b921a071"
    )
    nginx_http = (root / "deploy/nginx/casandra-api-http.conf").read_text()
    nginx_location = (root / "deploy/nginx/casandra-api-location.conf").read_text()
    nginx_server = (root / "deploy/nginx/casandra-standalone.conf").read_text()
    assert "limit_conn_zone $casandra_upload_global" in nginx_http
    assert "client_max_body_size 110032768" in nginx_location
    assert "limit_conn casandra_global_uploads 1" in nginx_location
    assert "listen 127.0.0.1:8082 proxy_protocol default_server" in nginx_server
    api_unit = (root / "deploy/systemd/casandra-web-api.service").read_text()
    worker_unit = (root / "deploy/systemd/casandra-web-worker.service").read_text()
    assert "MemoryMax=1536M" in api_unit
    assert "MemoryMax=5G" in worker_unit
    assert "CPUQuota=300%" in worker_unit
    assert "Environment=OMP_NUM_THREADS=3" in worker_unit
    assert "LimitFSIZE=2147483648" in worker_unit

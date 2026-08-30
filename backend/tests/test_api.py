import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx2 as httpx
import pytest

import casandra_web.service as service_module
from casandra_web.api import _forwarded_allow_ips, create_app
from casandra_web.db import Store
from casandra_web.fasta import FastaError, FastaRecord, NormalizedFasta
from casandra_web.models import JobSubmission
from casandra_web.service import JobService


@pytest.mark.asyncio
async def test_submit_authorize_and_cancel(settings):
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client,
    ):
        created = await client.post(
            "/casandra/api/v1/jobs",
            json={
                "sequence": ">contig_a private\nACGTACGTACGT",
                "filename": "../../sample.fa",
                "gene_mode": "meta",
            },
        )
        assert created.status_code == 202
        payload = created.json()
        job_id = payload["job"]["job_id"]
        token = payload["access_token"]
        assert payload["job"]["input"]["filename"] == "sample.fa"
        assert payload["job"]["options"]["gene_mode"] == "meta"

        missing = await client.get(f"/casandra/api/v1/jobs/{job_id}")
        assert missing.status_code == 401
        wrong = await client.get(
            f"/casandra/api/v1/jobs/{job_id}", headers={"Authorization": "Bearer wrong"}
        )
        assert wrong.status_code == 403
        ok = await client.get(
            f"/casandra/api/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"}
        )
        assert ok.status_code == 200
        assert ok.json()["status"] == "queued"

        cancelled = await client.delete(
            f"/casandra/api/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"}
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["job"]["status"] == "cancelled"

        stored = Store(settings).get_job(job_id)
        assert token not in str(stored)


@pytest.mark.asyncio
async def test_public_contract_and_security_headers(settings):
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client,
    ):
        config = await client.get("/casandra/api/v1/config")
        assert config.status_code == 200
        assert config.json()["casandra_is_authoritative"] is True
        assert config.json()["array_overlay_changes_cas_calls"] is False
        assert config.json()["max_header_characters"] == settings.max_header_characters
        assert config.json()["translation_table_scope"] == "single_mode_training_request"
        assert config.json()["analysis_modes"] == [
            "complete_genome",
            "annotate_cas_genes",
            "classify_cassette",
            "metagenomic",
        ]
        assert config.json()["max_protein_records"] == settings.max_protein_records
        assert config.json()["max_total_residues"] == settings.max_total_residues
        assert (
            config.json()["max_protein_request_bytes"]
            == settings.effective_protein_request_bytes
        )
        assert config.headers["x-frame-options"] == "DENY"
        version = (await client.get("/casandra/api/v1/version")).json()
        assert version["web_release_id"] == "b" * 64
        assert version["casandra_role"] == "authoritative_cas_caller"
        assert version["casandra_bundle_id"] == "fake-bundle"
        assert version["casandra_bundle_manifest_sha256"] == "a" * 64
        assert version["casandra_program_version"] == "0.3.0.dev0"
        assert version["casandra_schema_version"] == 5
        assert version["casandra_bundle_role"] == "deployment_refit"
        assert version["casandra_model"] == {
            "bundle_id": "fake-bundle",
            "bundle_manifest_sha256": "a" * 64,
            "program_version": "0.3.0.dev0",
            "schema_version": 5,
            "bundle_role": "deployment_refit",
        }
        assert config.json()["max_cas_only_request_bytes"] == settings.max_request_bytes
        assert config.json()["max_cas_only_total_bases"] == settings.max_total_bases
        assert config.json()["max_cas_only_record_bases"] == settings.max_record_bases
        assert config.json()["max_cas_only_records"] == settings.max_records
        assert config.json()["max_array_request_bytes"] == settings.max_request_bytes
        assert config.json()["max_array_total_bases"] == settings.max_total_bases
        assert config.json()["max_array_record_bases"] == settings.max_total_bases
        assert config.json()["max_array_records"] == settings.max_records
        assert config.json()["input_policies"] == {
            "cas_only": {
                "when": {"include_crispr_arrays": False},
                "max_request_bytes": settings.max_request_bytes,
                "max_total_bases": settings.max_total_bases,
                "max_record_bases": settings.max_record_bases,
                "max_records": settings.max_records,
            },
            "with_crispr_arrays": {
                "when": {"include_crispr_arrays": True},
                "max_request_bytes": settings.max_request_bytes,
                "max_total_bases": settings.max_total_bases,
                "max_record_bases": settings.max_total_bases,
                "max_records": settings.max_records,
            },
        }


@pytest.mark.asyncio
async def test_array_limits_are_stricter_without_reducing_cas_only_modes(settings):
    configured = replace(
        settings,
        max_request_bytes=1_000,
        max_total_bases=1_000,
        max_records=5,
        max_array_request_bytes=64,
        max_array_total_bases=10,
        max_array_records=1,
    )
    app = create_app(configured)
    sequence = ">record_a\nAAAAAAAA\n>record_b\nAAAAAAAA\n"
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client,
    ):
        complete = await client.post(
            "/casandra/api/v1/jobs",
            json={
                "analysis_mode": "complete_genome",
                "sequence": sequence,
                "include_crispr_arrays": False,
            },
        )
        assert complete.status_code == 202

        metagenomic = await client.post(
            "/casandra/api/v1/jobs",
            json={"analysis_mode": "metagenomic", "sequence": sequence},
        )
        assert metagenomic.status_code == 202

        array_job = await client.post(
            "/casandra/api/v1/jobs",
            json={
                "analysis_mode": "complete_genome",
                "sequence": sequence,
                "include_crispr_arrays": True,
            },
        )
        assert array_job.status_code == 422
        assert "too many FASTA records" in array_job.json()["detail"]

        config = (await client.get("/casandra/api/v1/config")).json()
        assert config["max_cas_only_request_bytes"] == 1_000
        assert config["max_cas_only_total_bases"] == 1_000
        assert config["max_cas_only_record_bases"] == 1_000
        assert config["max_cas_only_records"] == 5
        assert config["max_array_request_bytes"] == 64
        assert config["max_array_total_bases"] == 10
        assert config["max_array_record_bases"] == 10
        assert config["max_array_records"] == 1
        assert config["input_policies"]["cas_only"] == {
            "when": {"include_crispr_arrays": False},
            "max_request_bytes": 1_000,
            "max_total_bases": 1_000,
            "max_record_bases": 1_000,
            "max_records": 5,
        }
        assert config["input_policies"]["with_crispr_arrays"] == {
            "when": {"include_crispr_arrays": True},
            "max_request_bytes": 64,
            "max_total_bases": 10,
            "max_record_bases": 10,
            "max_records": 1,
        }


@pytest.mark.asyncio
async def test_large_body_allowance_does_not_raise_protein_upload_policy(settings):
    configured = replace(
        settings,
        max_request_bytes=1_000,
        max_total_bases=1_000,
        max_protein_request_bytes=64,
    )
    app = create_app(configured)
    sequence = ">record\n" + "A" * 70 + "\n"
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client,
    ):
        cas_only = await client.post(
            "/casandra/api/v1/jobs",
            json={"analysis_mode": "complete_genome", "sequence": sequence},
        )
        assert cas_only.status_code == 202

        protein = await client.post(
            "/casandra/api/v1/jobs",
            json={"analysis_mode": "annotate_cas_genes", "sequence": sequence},
        )
        assert protein.status_code == 422
        assert "upload limit" in protein.json()["detail"]

        config = (await client.get("/casandra/api/v1/config")).json()
        assert config["max_cas_only_request_bytes"] == 1_000
        assert config["max_protein_request_bytes"] == 64


def test_hundred_million_base_boundary_routes_only_to_cas_only_policy(
    settings, monkeypatch
):
    configured = replace(
        settings,
        max_request_bytes=110_000_000,
        max_total_bases=100_000_000,
        max_record_bases=100_000_000,
        max_records=10_000,
        max_array_request_bytes=4_500_000,
        max_array_total_bases=2_000_000,
        max_array_records=20,
        max_retained_input_bases=250_000_000,
    )
    calls = []

    def boundary_normalizer(value, **limits):
        del value
        calls.append(limits)
        if limits["max_total_bases"] < 100_000_000:
            raise FastaError("Input exceeds the configured total base limit")
        return NormalizedFasta(
            data=b">boundary\nA\n",
            records=(FastaRecord(source_id="boundary", sequence="A"),),
            base_count=100_000_000,
            sha256="b" * 64,
        )

    monkeypatch.setattr(service_module, "normalize_fasta", boundary_normalizer)
    store = Store(configured)
    store.initialize()
    service = JobService(configured, store)
    created = service.submit(
        JobSubmission(
            analysis_mode="complete_genome",
            sequence=">boundary\nA\n",
            include_crispr_arrays=False,
        ),
        "192.0.2.100",
    )
    assert created.job.input.base_count == 100_000_000
    assert calls[-1] == {
        "max_request_bytes": 110_000_000,
        "max_total_bases": 100_000_000,
        "max_record_bases": 100_000_000,
        "max_records": 10_000,
        "max_header_characters": configured.max_header_characters,
    }

    with pytest.raises(FastaError, match="total base limit"):
        service.submit(
            JobSubmission(
                analysis_mode="complete_genome",
                sequence=">boundary\nA\n",
                include_crispr_arrays=True,
            ),
            "192.0.2.101",
        )
    assert calls[-1]["max_request_bytes"] == 4_500_000
    assert calls[-1]["max_total_bases"] == 2_000_000
    assert calls[-1]["max_records"] == 20


@pytest.mark.asyncio
async def test_cors_is_exact(settings):
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client,
    ):
        allowed = await client.options(
            "/casandra/api/v1/jobs",
            headers={
                "Origin": "https://example.github.io",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "https://example.github.io"
        denied = await client.options(
            "/casandra/api/v1/jobs",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert denied.status_code == 400


@pytest.mark.asyncio
async def test_expired_result_is_unavailable_before_cleanup(settings):
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client,
    ):
        created = await client.post(
            "/casandra/api/v1/jobs",
            json={"sequence": ">a\nACGTACGT", "filename": "a.fa"},
        )
        payload = created.json()
        job_id = payload["job"]["job_id"]
        token = payload["access_token"]
        expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with sqlite3.connect(settings.database_path) as connection:
            connection.execute(
                "UPDATE jobs SET status='cancelled', phase='cancelled', expires_at=? WHERE job_id=?",
                (expired, job_id),
            )

        response = await client.get(
            f"/casandra/api/v1/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 410
        assert response.json()["detail"] == "Job results have expired"


def test_forwarded_proxy_allowlist_accepts_only_exact_ips(monkeypatch):
    monkeypatch.setenv("CASANDRA_WEB_FORWARDED_ALLOW_IPS", "172.30.249.2,127.0.0.1")
    assert _forwarded_allow_ips() == "172.30.249.2,127.0.0.1"
    monkeypatch.setenv("CASANDRA_WEB_FORWARDED_ALLOW_IPS", "*")
    with pytest.raises(ValueError):
        _forwarded_allow_ips()


@pytest.mark.asyncio
async def test_protein_submission_has_mode_aware_metadata_and_validation(settings):
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client,
    ):
        created = await client.post(
            "/casandra/api/v1/jobs",
            json={
                "analysis_mode": "annotate_cas_genes",
                "sequence": ">cas_a\nMKTW\n>noncas_b\nACDX*",
                "filename": "proteins.faa",
            },
        )
        assert created.status_code == 202
        job = created.json()["job"]
        assert job["options"] == {
            "analysis_mode": "annotate_cas_genes",
            "include_crispr_arrays": False,
            "gene_mode": None,
            "translation_table": None,
            "translation_table_scope": None,
        }
        assert job["input"]["input_kind"] == "protein_fasta"
        assert job["input"]["sequence_unit"] == "aa"
        assert job["input"]["base_count"] is None
        assert job["input"]["residue_count"] == 8

        invalid_arrays = await client.post(
            "/casandra/api/v1/jobs",
            json={
                "analysis_mode": "metagenomic",
                "sequence": ">contig\nACGT",
                "include_crispr_arrays": True,
            },
        )
        assert invalid_arrays.status_code == 422


def test_new_and_legacy_submission_defaults_are_distinct():
    from casandra_web.models import JobSubmission

    new = JobSubmission(analysis_mode="complete_genome", sequence="ACGT")
    assert new.gene_mode == "single"
    assert new.include_crispr_arrays is False

    legacy = JobSubmission(sequence="ACGT")
    assert legacy.gene_mode == "auto"
    assert legacy.include_crispr_arrays is True

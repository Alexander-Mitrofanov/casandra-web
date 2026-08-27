import sqlite3
from datetime import datetime, timedelta, timezone

import httpx2 as httpx
import pytest

from casandra_web.api import _forwarded_allow_ips, create_app
from casandra_web.db import Store


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
        assert config.headers["x-frame-options"] == "DENY"
        version = (await client.get("/casandra/api/v1/version")).json()
        assert version["casandra_role"] == "authoritative_cas_caller"


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

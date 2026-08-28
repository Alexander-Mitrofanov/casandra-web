"""FastAPI control plane. Scientific programs run only in the worker."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from ipaddress import ip_address
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.datastructures import Headers, MutableHeaders

from . import __version__
from .config import Settings
from .db import CapacityError, StorageCapacityError, Store
from .fasta import FastaError
from .models import (
    AnalysisMode,
    CancelResponse,
    GeneMode,
    HealthResponse,
    JobCreated,
    JobSubmission,
    JobView,
    PublicConfig,
    VersionResponse,
)
from .service import AuthorizationError, ExpiredError, JobService, NotFoundError

API_PREFIX = "/casandra/api/v1"


def _forwarded_allow_ips() -> str:
    raw = os.getenv("CASANDRA_WEB_FORWARDED_ALLOW_IPS", "127.0.0.1")
    addresses = [value.strip() for value in raw.split(",") if value.strip()]
    if not addresses or len(addresses) > 8:
        raise ValueError("CASANDRA_WEB_FORWARDED_ALLOW_IPS must contain 1 to 8 IP addresses")
    for address in addresses:
        ip_address(address)
    return ",".join(addresses)


class _BodyTooLarge(RuntimeError):
    pass


class SecurityBoundaryMiddleware:
    """Pure ASGI request limit and response-header boundary."""

    def __init__(self, app, *, max_body_bytes: int):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        declared = headers.get("content-length")
        if declared is not None:
            try:
                declared_bytes = int(declared)
            except ValueError:
                await JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})(
                    scope, receive, send
                )
                return
            if declared_bytes > self.max_body_bytes:
                await JSONResponse(
                    status_code=413, content={"detail": "Request body is too large"}
                )(scope, receive, send)
                return
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise _BodyTooLarge()
            return message

        async def secure_send(message):
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers["X-Content-Type-Options"] = "nosniff"
                response_headers["X-Frame-Options"] = "DENY"
                response_headers["Referrer-Policy"] = "no-referrer"
                response_headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                response_headers["Cache-Control"] = "no-store"
            await send(message)

        try:
            await self.app(scope, limited_receive, secure_send)
        except _BodyTooLarge:
            await JSONResponse(status_code=413, content={"detail": "Request body is too large"})(
                scope, receive, secure_send
            )


async def _bearer(authorization: Annotated[str | None, Header()] = None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A bearer job access token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:]
    if not token or len(token) > 256 or any(character.isspace() for character in token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")
    return token


def _client_address(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings.from_env()
    store = Store(configured)
    service = JobService(configured, store)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        store.initialize()
        yield

    app = FastAPI(
        title="CasAndra Web API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = configured
    app.state.store = store
    app.state.service = service
    app.add_middleware(
        SecurityBoundaryMiddleware,
        max_body_bytes=configured.max_request_bytes + 32_768,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(configured.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition", "Content-Length"],
        max_age=600,
    )

    @app.exception_handler(FastaError)
    async def fasta_error(_request: Request, error: FastaError):
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(CapacityError)
    async def capacity_error(_request: Request, error: CapacityError):
        return JSONResponse(
            status_code=429, content={"detail": str(error)}, headers={"Retry-After": "60"}
        )

    @app.exception_handler(StorageCapacityError)
    async def storage_capacity_error(_request: Request, error: StorageCapacityError):
        return JSONResponse(
            status_code=503, content={"detail": str(error)}, headers={"Retry-After": "900"}
        )

    @app.exception_handler(NotFoundError)
    async def not_found(_request: Request, _error: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    @app.exception_handler(AuthorizationError)
    async def authorization_error(_request: Request, _error: AuthorizationError):
        return JSONResponse(status_code=403, content={"detail": "Invalid job access token"})

    @app.exception_handler(ExpiredError)
    async def expired_error(_request: Request, _error: ExpiredError):
        return JSONResponse(status_code=410, content={"detail": "Job results have expired"})

    @app.get(f"{API_PREFIX}/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        database = "ok" if store.ping() else "error"
        worker = store.worker_state() if database == "ok" else "error"
        return HealthResponse(
            status="ok" if database == "ok" and worker == "ok" else "degraded",
            database=database,
            worker=worker,
            service=configured.service_name,
            version=__version__,
        )

    @app.get(f"{API_PREFIX}/config", response_model=PublicConfig)
    async def public_config() -> PublicConfig:
        return PublicConfig(
            service=configured.service_name,
            api_version=configured.api_version,
            analysis_modes=list(AnalysisMode),
            gene_modes=list(GeneMode),
            max_request_bytes=configured.max_request_bytes,
            max_total_bases=configured.max_total_bases,
            max_record_bases=configured.max_record_bases,
            max_total_residues=configured.max_total_residues,
            max_record_residues=configured.max_protein_residues,
            max_protein_residues=configured.max_protein_residues,
            max_protein_records=configured.max_protein_records,
            max_records=configured.max_records,
            max_header_characters=configured.max_header_characters,
            max_queued_jobs=configured.max_queued_jobs,
            max_active_jobs=configured.max_active_jobs,
            max_active_jobs_per_client=configured.max_active_jobs_per_client,
            retention_seconds=configured.retention_seconds,
            max_retained_jobs=configured.max_retained_jobs,
            submission_window_seconds=configured.submission_window_seconds,
            max_submissions_per_window=configured.max_submissions_per_window,
            max_job_lifetime_seconds=configured.max_job_lifetime_seconds,
        )

    @app.get(f"{API_PREFIX}/version", response_model=VersionResponse)
    async def version() -> VersionResponse:
        return VersionResponse(
            service=configured.service_name,
            version=__version__,
            api_version=configured.api_version,
            casandra_role="authoritative_cas_caller",
            crispridentify_role="independent_array_overlay",
        )

    @app.post(f"{API_PREFIX}/jobs", response_model=JobCreated, status_code=202)
    async def create_job(submission: JobSubmission, request: Request) -> JobCreated:
        return service.submit(submission, _client_address(request))

    @app.get(f"{API_PREFIX}/jobs/{{job_id}}", response_model=JobView)
    async def get_job(job_id: str, token: Annotated[str, Depends(_bearer)]) -> JobView:
        return service.get(job_id, token)

    @app.delete(f"{API_PREFIX}/jobs/{{job_id}}", response_model=CancelResponse)
    async def cancel_job(job_id: str, token: Annotated[str, Depends(_bearer)]) -> CancelResponse:
        return CancelResponse(job=service.cancel(job_id, token))

    @app.get(f"{API_PREFIX}/jobs/{{job_id}}/artifacts/{{artifact_id}}")
    async def artifact(job_id: str, artifact_id: str, token: Annotated[str, Depends(_bearer)]):
        path, metadata = service.artifact_path(job_id, token, artifact_id)
        return FileResponse(
            path,
            media_type=str(metadata["media_type"]),
            filename=str(metadata["name"]),
        )

    @app.get(f"{API_PREFIX}/jobs/{{job_id}}/result")
    async def result_bundle(job_id: str, token: Annotated[str, Depends(_bearer)]):
        service.authorize(job_id, token)
        archive = next(
            (
                item
                for item in store.list_artifacts(job_id)
                if item["name"] == "casandra-results.zip"
            ),
            None,
        )
        if archive is None:
            raise NotFoundError("Result bundle not found")
        path, metadata = service.artifact_path(job_id, token, str(archive["artifact_id"]))
        return FileResponse(path, media_type="application/zip", filename=str(metadata["name"]))

    return app


app = create_app()


def main() -> None:
    import uvicorn

    port = int(os.getenv("CASANDRA_WEB_PORT", "8010"))
    host = os.getenv("CASANDRA_WEB_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "0.0.0.0"}:
        raise ValueError("CASANDRA_WEB_HOST must be 127.0.0.1 or 0.0.0.0")
    uvicorn.run(
        "casandra_web.api:app",
        host=host,
        port=port,
        proxy_headers=True,
        forwarded_allow_ips=_forwarded_allow_ips(),
        access_log=False,
    )


if __name__ == "__main__":
    main()

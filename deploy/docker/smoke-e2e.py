#!/usr/bin/env python3
"""Credential-safe end-to-end smoke through the loopback PROXY-v2 edge."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import socket
import struct
import time
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

API = "/casandra/api/v1"
TERMINAL = {"completed", "failed", "cancelled"}


class ProxyV2Connection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, source_ip: str, timeout: float = 30):
        super().__init__(host, port, timeout=timeout)
        self.source_ip = source_ip

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self.host, self.port), self.timeout, self.source_address
        )
        source = ipaddress.ip_address(self.source_ip)
        destination = ipaddress.ip_address("127.0.0.1")
        if source.version != 4:
            raise ValueError("the deployment smoke currently requires an IPv4 source")
        signature = b"\r\n\r\n\x00\r\nQUIT\n"
        header = struct.pack(
            "!12sBBH4s4sHH",
            signature,
            0x21,
            0x11,
            12,
            source.packed,
            destination.packed,
            49152,
            443,
        )
        self.sock.sendall(header)


def request(
    args: argparse.Namespace,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: object | None = None,
    origin: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    encoded = None
    headers = {"Accept": "application/json", "Host": "casandra-smoke.invalid"}
    if body is not None:
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin
    if extra_headers:
        headers.update(extra_headers)
    connection = ProxyV2Connection(args.host, args.port, args.source_ip)
    try:
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        return response.status, {key.lower(): value for key, value in response.getheaders()}, payload
    finally:
        connection.close()


def json_body(status: int, payload: bytes, expected: set[int]) -> Any:
    if status not in expected:
        excerpt = payload[:500].decode("utf-8", errors="replace")
        raise RuntimeError(f"unexpected HTTP status {status}: {excerpt}")
    try:
        return json.loads(payload)
    except json.JSONDecodeError as error:
        raise RuntimeError("endpoint returned invalid JSON") from error


def authorized_get(
    args: argparse.Namespace, path: str, token: str
) -> tuple[dict[str, str], bytes]:
    status, headers, payload = request(args, "GET", path, token=token, origin=args.origin)
    if status != 200:
        raise RuntimeError(f"authorized request returned unexpected HTTP status {status}")
    return headers, payload


def submit(args: argparse.Namespace, sequence: str, filename: str) -> tuple[str, str]:
    status, headers, payload = request(
        args,
        "POST",
        f"{API}/jobs",
        body={"sequence": sequence, "filename": filename, "gene_mode": "auto"},
        origin=args.origin,
    )
    value = json_body(status, payload, {202})
    if headers.get("access-control-allow-origin") != args.origin:
        raise RuntimeError("submission response did not preserve the exact reviewed CORS origin")
    job_id = value.get("job", {}).get("job_id")
    token = value.get("access_token")
    if not isinstance(job_id, str) or not isinstance(token, str):
        raise TypeError("submission did not return a private job capability")
    return job_id, token


def wait_for_terminal(
    args: argparse.Namespace, job_id: str, token: str, timeout: int
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    previous: tuple[str | None, str | None] | None = None
    while time.monotonic() < deadline:
        status, _headers, payload = request(
            args, "GET", f"{API}/jobs/{job_id}", token=token, origin=args.origin
        )
        value = json_body(status, payload, {200})
        state = (value.get("status"), value.get("phase"))
        if state != previous:
            print(f"job {job_id}: status={state[0]} phase={state[1]}", flush=True)
            previous = state
        if state[0] in TERMINAL:
            return value
        time.sleep(args.poll_seconds)
    raise TimeoutError(f"job {job_id} did not finish within {timeout} seconds")


def verify_completed_job(
    args: argparse.Namespace, job_id: str, token: str, job: dict[str, Any]
) -> None:
    if job.get("status") != "completed":
        raise RuntimeError(f"scientific smoke did not complete: {job.get('error')}")
    summary = job.get("summary")
    if not isinstance(summary, dict) or summary.get("schema_version") != "1.0.0":
        raise RuntimeError("completed job lacks the reviewed public summary schema")
    provenance = summary.get("provenance", {})
    if (
        provenance.get("casandra_schema_version") != 5
        or provenance.get("crispridentify_version") != "2.0.0"
        or provenance.get("array_overlay_role") != "independent_coordinate_overlay"
    ):
        raise RuntimeError("completed job lacks reviewed scientific provenance")
    if "protein_sequence" in json.dumps(summary):
        raise RuntimeError("public summary exposed a protein sequence")

    artifacts = job.get("artifacts")
    if not isinstance(artifacts, list):
        raise TypeError("completed job lacks artifact metadata")
    by_name = {item.get("name"): item for item in artifacts if isinstance(item, dict)}
    for required in ("casandra-run.json", "crispr-arrays.json", "casandra-results.zip"):
        if required not in by_name:
            raise RuntimeError(f"completed job lacks {required}")

    run_item = by_name["casandra-run.json"]
    _headers, run_payload = authorized_get(args, run_item["download_url"], token)
    run = json.loads(run_payload)
    if run.get("schema_version") != 5:
        raise RuntimeError("real CasAndra artifact is not schema 5")

    array_item = by_name["crispr-arrays.json"]
    _headers, array_payload = authorized_get(args, array_item["download_url"], token)
    arrays = json.loads(array_payload)
    if not isinstance(arrays.get("arrays"), list):
        raise TypeError("complete sequence-free CRISPR array artifact is invalid")
    if len(arrays["arrays"]) != summary.get("overview", {}).get("crispr_array_count"):
        raise RuntimeError("complete CRISPR array artifact disagrees with the summary count")

    zip_item = by_name["casandra-results.zip"]
    _headers, archive_payload = authorized_get(args, zip_item["download_url"], token)
    if hashlib.sha256(archive_payload).hexdigest() != zip_item.get("sha256"):
        raise RuntimeError("downloaded archive digest disagrees with artifact metadata")
    with zipfile.ZipFile(BytesIO(archive_payload)) as archive:
        if archive.testzip() is not None or "result-summary.json" not in archive.namelist():
            raise RuntimeError("downloaded result archive failed integrity checks")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fasta", type=Path, required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8082)
    parser.add_argument("--source-ip", default="203.0.113.10")
    parser.add_argument("--timeout", type=int, default=10_800)
    parser.add_argument("--poll-seconds", type=float, default=5)
    args = parser.parse_args()
    sequence = args.fasta.read_text(encoding="ascii")

    status, _headers, payload = request(args, "GET", f"{API}/health")
    health = json_body(status, payload, {200})
    if health.get("status") != "ok":
        raise RuntimeError(f"service is not ready: {health}")

    status, headers, _payload = request(
        args,
        "OPTIONS",
        f"{API}/jobs",
        origin=args.origin,
        extra_headers={
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    if status != 200 or headers.get("access-control-allow-origin") != args.origin:
        raise RuntimeError("exact-origin CORS preflight failed")

    job_id, token = submit(args, sequence, args.fasta.name)
    print(f"submitted real scientific job {job_id}", flush=True)
    wrong_status, _headers, _payload = request(
        args, "GET", f"{API}/jobs/{job_id}", token="deliberately-wrong-token"
    )
    if wrong_status != 403:
        raise RuntimeError("wrong-token access was not rejected")
    completed = wait_for_terminal(args, job_id, token, args.timeout)
    verify_completed_job(args, job_id, token, completed)

    cancel_sequence = ">cancel_probe\n" + "ACGT" * 50_000 + "\n"
    cancel_id, cancel_token = submit(args, cancel_sequence, "cancel-probe.fasta")
    status, _headers, payload = request(
        args,
        "DELETE",
        f"{API}/jobs/{cancel_id}",
        token=cancel_token,
        origin=args.origin,
    )
    cancelled = json_body(status, payload, {200}).get("job", {})
    if cancelled.get("status") not in {"running", "cancelled"}:
        raise RuntimeError("cancellation request returned an unexpected job state")
    cancelled = wait_for_terminal(args, cancel_id, cancel_token, 300)
    if cancelled.get("status") != "cancelled":
        raise RuntimeError("cancellation smoke did not reach cancelled state")

    overview = completed["summary"]["overview"]
    print(
        "E2E passed: "
        f"Cas proteins={overview.get('cas_protein_count')}, "
        f"cassettes={overview.get('cassette_count')}, "
        f"CRISPR arrays={overview.get('crispr_array_count')}; "
        "schema 5, artifacts, CORS, authorization, and cancellation verified.",
        flush=True,
    )


if __name__ == "__main__":
    main()

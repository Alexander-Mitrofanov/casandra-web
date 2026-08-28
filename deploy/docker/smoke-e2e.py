#!/usr/bin/env python3
"""Credential-safe E2E smoke through loopback PROXY-v2 or public HTTPS."""

from __future__ import annotations

import argparse
import csv
import hashlib
import http.client
import ipaddress
import json
import socket
import struct
import time
import zipfile
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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


def connection_for(args: argparse.Namespace) -> http.client.HTTPConnection:
    if args.api_origin:
        parsed = urlsplit(args.api_origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("--api-origin must be an HTTPS origin without a path")
        return http.client.HTTPSConnection(
            parsed.hostname,
            parsed.port or 443,
            timeout=30,
        )
    return ProxyV2Connection(args.host, args.port, args.source_ip)


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
    headers = {"Accept": "application/json"}
    if not args.api_origin:
        headers["Host"] = "casandra-smoke.invalid"
    if body is not None:
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin
    if extra_headers:
        headers.update(extra_headers)
    connection = connection_for(args)
    try:
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        return (
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            payload,
        )
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


def authorized_get(args: argparse.Namespace, path: str, token: str) -> tuple[dict[str, str], bytes]:
    status, headers, payload = request(args, "GET", path, token=token, origin=args.origin)
    if status != 200:
        raise RuntimeError(f"authorized request returned unexpected HTTP status {status}")
    return headers, payload


def verify_preferred_exports(
    args: argparse.Namespace,
    token: str,
    by_name: dict[str, dict[str, Any]],
    analysis_mode: str,
    required_fasta: set[str],
) -> dict[str, Any]:
    required = {"casandra-results.json", "casandra-results.csv", *required_fasta}
    if not required.issubset(by_name):
        missing = ", ".join(sorted(required.difference(by_name)))
        raise RuntimeError(f"{analysis_mode} lacks preferred export artifacts: {missing}")

    expected_metadata = {
        "casandra-results.json": ("results", "json"),
        "casandra-results.csv": ("results", "csv"),
        **{name: ("sequences", "fasta") for name in required_fasta},
    }
    for name, (role, output_format) in expected_metadata.items():
        item = by_name[name]
        if (
            item.get("role") != role
            or item.get("format") != output_format
            or item.get("authoritative") is not True
        ):
            raise RuntimeError(f"{name} lacks authoritative presentation metadata")

    detail_headers, detail_payload = authorized_get(
        args, by_name["casandra-results.json"]["download_url"], token
    )
    if "no-store" not in detail_headers.get("cache-control", ""):
        raise RuntimeError("complete result download is not protected by no-store caching")
    try:
        detail = json.loads(detail_payload)
    except json.JSONDecodeError as error:
        raise RuntimeError("complete result export is not valid JSON") from error
    if (
        not isinstance(detail, dict)
        or detail.get("schema_version") != "1.0.0"
        or detail.get("analysis_mode") != analysis_mode
        or not isinstance(detail.get("sources"), list)
        or not isinstance(detail.get("features"), list)
    ):
        raise RuntimeError(f"{analysis_mode} complete result export has an invalid contract")
    for feature in detail["features"]:
        if not isinstance(feature, dict) or not isinstance(feature.get("sequences"), list):
            raise TypeError("complete result contains a feature without sequence detail state")
        if feature.get("kind") in {"cas_gene", "protein", "crispr_array"}:
            sequences = feature["sequences"]
            if not sequences or any(
                not isinstance(sequence, dict)
                or not isinstance(sequence.get("sequence"), str)
                or not sequence["sequence"]
                for sequence in sequences
            ):
                raise RuntimeError("interactive biological feature lacks its sequence contents")

    _headers, csv_payload = authorized_get(
        args, by_name["casandra-results.csv"]["download_url"], token
    )
    try:
        rows = list(csv.DictReader(StringIO(csv_payload.decode("utf-8"))))
    except (UnicodeError, csv.Error) as error:
        raise RuntimeError("complete result export is not valid UTF-8 CSV") from error
    if len(rows) != len(detail["features"]):
        raise RuntimeError("CSV and JSON complete exports disagree on feature count")

    for name in required_fasta:
        _headers, fasta_payload = authorized_get(args, by_name[name]["download_url"], token)
        try:
            text = fasta_payload.decode("ascii")
        except UnicodeError as error:
            raise RuntimeError(f"{name} is not ASCII FASTA") from error
        if text and (not text.startswith(">") or "\r" in text):
            raise RuntimeError(f"{name} does not have normalized FASTA framing")
    return detail


def submit(
    args: argparse.Namespace,
    sequence: str,
    filename: str,
    *,
    analysis_mode: str,
    include_crispr_arrays: bool,
) -> tuple[str, str]:
    status, headers, payload = request(
        args,
        "POST",
        f"{API}/jobs",
        body={
            "analysis_mode": analysis_mode,
            "sequence": sequence,
            "filename": filename,
            "include_crispr_arrays": include_crispr_arrays,
        },
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


def source_variant(args: argparse.Namespace, offset: int) -> argparse.Namespace:
    """Use a distinct reviewed PROXY client for each rate-limited smoke job."""

    if args.api_origin:
        return args
    value = int(ipaddress.IPv4Address(args.source_ip)) + offset
    if value > int(ipaddress.IPv4Address("255.255.255.255")):
        raise ValueError("--source-ip does not leave room for smoke client variants")
    return argparse.Namespace(**{**vars(args), "source_ip": str(ipaddress.IPv4Address(value))})


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
    if not isinstance(summary, dict) or summary.get("schema_version") != "1.1.0":
        raise RuntimeError("completed job lacks the reviewed public summary schema")
    if (
        summary.get("analysis_mode") != "complete_genome"
        or summary.get("include_crispr_arrays") is not True
    ):
        raise RuntimeError("completed job lacks the requested complete-genome contract")
    provenance = summary.get("provenance", {})
    if (
        provenance.get("casandra_schema_version") != 5
        or provenance.get("crispridentify_version") != "2.0.0"
        or provenance.get("array_overlay_role") != "independent_coordinate_overlay"
        or provenance.get("array_detection") != {"requested": True, "status": "completed"}
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

    preferred_fasta = {"cas-proteins.faa", "cas-coding-sequences.fna"}
    if summary.get("overview", {}).get("crispr_array_count", 0) > 0:
        preferred_fasta.update({"crispr-arrays.fna", "crispr-components.fna"})
    detail = verify_preferred_exports(args, token, by_name, "complete_genome", preferred_fasta)
    detail_kinds = [feature.get("kind") for feature in detail["features"]]
    if detail_kinds.count("cas_gene") != summary.get("overview", {}).get(
        "cas_protein_count"
    ) or detail_kinds.count("crispr_array") != summary.get("overview", {}).get(
        "crispr_array_count"
    ):
        raise RuntimeError("complete interactive result disagrees with public overview counts")

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


def verify_non_array_job(
    job: dict[str, Any], analysis_mode: str
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if job.get("status") != "completed":
        raise RuntimeError(f"{analysis_mode} smoke did not complete: {job.get('error')}")
    summary = job.get("summary")
    if (
        not isinstance(summary, dict)
        or summary.get("schema_version") != "1.1.0"
        or summary.get("analysis_mode") != analysis_mode
        or summary.get("include_crispr_arrays") is not False
    ):
        raise RuntimeError(f"{analysis_mode} lacks the reviewed public summary contract")
    provenance = summary.get("provenance")
    if not isinstance(provenance, dict) or (
        provenance.get("casandra_program_version") != "0.3.0.dev0"
        or provenance.get("array_detection") != {"requested": False, "status": "not_requested"}
    ):
        raise RuntimeError(f"{analysis_mode} lacks reviewed scientific provenance")
    if "protein_sequence" in json.dumps(summary):
        raise RuntimeError(f"{analysis_mode} public summary exposed a protein sequence")
    artifacts = job.get("artifacts")
    if not isinstance(artifacts, list):
        raise TypeError(f"{analysis_mode} lacks artifact metadata")
    by_name = {str(item.get("name")): item for item in artifacts if isinstance(item, dict)}
    if any(name.startswith("crispr") for name in by_name):
        raise RuntimeError(f"{analysis_mode} unexpectedly published CRISPR artifacts")
    return summary, by_name


def verify_prediction_rows(rows: object, expected_ids: list[str], *, coordinate_free: bool) -> None:
    if not isinstance(rows, list) or [row.get("protein_id") for row in rows] != expected_ids:
        raise RuntimeError("protein predictions do not preserve every submitted record in order")
    coordinate_keys = {"contig_id", "start", "end", "strand", "cassette_id"}
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("protein prediction is not an object")
        result = row.get("result")
        if row.get("is_cas") is True:
            if not isinstance(result, str) or not result or result != row.get("cas_family"):
                raise RuntimeError(
                    "positive protein prediction lacks its literal Cas-family result"
                )
        elif row.get("is_cas") is False:
            if result != "no cas" or row.get("cas_family") is not None:
                raise RuntimeError("negative protein prediction lacks exact no cas result")
        else:
            raise RuntimeError("protein prediction lacks a boolean Cas call")
        if coordinate_free and coordinate_keys.intersection(row):
            raise RuntimeError("protein-only prediction invented genomic coordinates")


def verify_annotation_job(
    args: argparse.Namespace, token: str, job: dict[str, Any], expected_ids: list[str]
) -> None:
    summary, by_name = verify_non_array_job(job, "annotate_cas_genes")
    verify_prediction_rows(summary.get("protein_predictions"), expected_ids, coordinate_free=True)
    required = {
        "result-summary.json",
        "protein-predictions.jsonl",
        "casandra-run.json",
        "casandra-manifest.json",
        "casandra-results.zip",
    }
    if not required.issubset(by_name):
        raise RuntimeError("annotation smoke lacks provenance-bearing artifacts")
    detail = verify_preferred_exports(
        args,
        token,
        by_name,
        "annotate_cas_genes",
        {"all-proteins.faa", "cas-proteins.faa"},
    )
    if [
        feature.get("protein_id")
        for feature in detail["features"]
        if feature.get("kind") == "protein"
    ] != expected_ids:
        raise RuntimeError("annotation interactive result changed submitted protein order")
    _headers, payload = authorized_get(
        args, by_name["protein-predictions.jsonl"]["download_url"], token
    )
    rows = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line]
    artifact_ids = [str(row.get("sequence_id")) for row in rows]
    if artifact_ids != expected_ids or any(
        row.get("result") != (row.get("cas_family") if row.get("is_cas") else "no cas")
        for row in rows
    ):
        raise RuntimeError("annotation JSONL lacks literal ordered result values")


def verify_cassette_job(
    args: argparse.Namespace,
    token: str,
    job: dict[str, Any],
    expected_ids: list[str],
) -> None:
    summary, by_name = verify_non_array_job(job, "classify_cassette")
    verify_prediction_rows(summary.get("protein_predictions"), expected_ids, coordinate_free=True)
    classification = summary.get("cassette_classification")
    if not isinstance(classification, dict) or (
        classification.get("order_used_for_architecture") is not True
        or classification.get("coordinates_available") is not False
        or not isinstance(classification.get("result"), str)
    ):
        raise RuntimeError("cassette smoke lacks ordered coordinate-free classification")
    required = {
        "result-summary.json",
        "protein-predictions.jsonl",
        "cassette-classification.json",
        "casandra-run.json",
        "casandra-manifest.json",
        "casandra-results.zip",
    }
    if not required.issubset(by_name):
        raise RuntimeError("cassette smoke lacks its reviewed artifact set")
    detail = verify_preferred_exports(
        args,
        token,
        by_name,
        "classify_cassette",
        {"cassette-proteins.faa", "cassette-cas-proteins.faa"},
    )
    if [
        feature.get("protein_id")
        for feature in detail["features"]
        if feature.get("kind") == "protein"
    ] != expected_ids:
        raise RuntimeError("cassette interactive result changed submitted protein order")


def verify_metagenomic_job(
    args: argparse.Namespace,
    token: str,
    job: dict[str, Any],
    expected_ids: list[str],
) -> None:
    summary, by_name = verify_non_array_job(job, "metagenomic")
    sequence_results = summary.get("sequence_results")
    if (
        not isinstance(sequence_results, list)
        or [row.get("sequence_id") for row in sequence_results if isinstance(row, dict)]
        != expected_ids
    ):
        raise RuntimeError("metagenomic smoke did not report every sequence separately")
    required = {
        "result-summary.json",
        "cas_proteins.tsv",
        "cassettes.tsv",
        "casandra.gff3",
        "casandra-run.json",
        "casandra-manifest.json",
        "casandra-results.zip",
    }
    if not required.issubset(by_name):
        raise RuntimeError("metagenomic smoke lacks its reviewed artifact set")
    detail = verify_preferred_exports(
        args,
        token,
        by_name,
        "metagenomic",
        {"cas-proteins.faa", "cas-coding-sequences.fna"},
    )
    if [source.get("id") for source in detail["sources"]] != expected_ids:
        raise RuntimeError("metagenomic interactive result changed independent source order")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fasta", type=Path, required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8082)
    parser.add_argument("--source-ip", default="203.0.113.10")
    parser.add_argument(
        "--api-origin",
        help="public HTTPS API origin; when set, bypasses local PROXY-v2 transport",
    )
    parser.add_argument("--timeout", type=int, default=10_800)
    parser.add_argument("--poll-seconds", type=float, default=5)
    args = parser.parse_args()
    sequence = args.fasta.read_text(encoding="ascii")

    status, _headers, payload = request(args, "GET", f"{API}/health")
    health = json_body(status, payload, {200})
    if health.get("status") != "ok":
        raise RuntimeError(f"service is not ready: {health}")

    status, _headers, payload = request(args, "GET", f"{API}/config")
    config = json_body(status, payload, {200})
    expected_modes = {
        "complete_genome",
        "annotate_cas_genes",
        "classify_cassette",
        "metagenomic",
    }
    if set(config.get("analysis_modes", [])) != expected_modes:
        raise RuntimeError("service does not expose the reviewed four-mode contract")

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

    job_id, token = submit(
        args,
        sequence,
        args.fasta.name,
        analysis_mode="complete_genome",
        include_crispr_arrays=True,
    )
    print(f"submitted real scientific job {job_id}", flush=True)
    wrong_status, _headers, _payload = request(
        args, "GET", f"{API}/jobs/{job_id}", token="deliberately-wrong-token"
    )
    if wrong_status != 403:
        raise RuntimeError("wrong-token access was not rejected")
    completed = wait_for_terminal(args, job_id, token, args.timeout)
    verify_completed_job(args, job_id, token, completed)

    if args.api_origin:
        print(
            "Public transport verified the complete-genome route; run the default "
            "local PROXY-v2 smoke as the required four-mode release gate.",
            flush=True,
        )
    else:
        protein_sequence = (
            ">protein_alpha\nMKTWACDEFGHIKLMNPQRSTVWY\n>protein_beta\nACDEFGHIKLMNPQRSTVWYBXZ\n"
        )
        protein_ids = ["protein_alpha", "protein_beta"]

        annotation_args = source_variant(args, 1)
        annotation_id, annotation_token = submit(
            annotation_args,
            protein_sequence,
            "annotation-smoke.faa",
            analysis_mode="annotate_cas_genes",
            include_crispr_arrays=False,
        )
        print(f"submitted real annotation job {annotation_id}", flush=True)
        annotation = wait_for_terminal(
            annotation_args, annotation_id, annotation_token, args.timeout
        )
        verify_annotation_job(annotation_args, annotation_token, annotation, protein_ids)

        cassette_args = source_variant(args, 2)
        cassette_id, cassette_token = submit(
            cassette_args,
            protein_sequence,
            "cassette-smoke.faa",
            analysis_mode="classify_cassette",
            include_crispr_arrays=False,
        )
        print(f"submitted real cassette job {cassette_id}", flush=True)
        cassette = wait_for_terminal(cassette_args, cassette_id, cassette_token, args.timeout)
        verify_cassette_job(cassette_args, cassette_token, cassette, protein_ids)

        coding_sequence = "ATG" + "GCT" * 120 + "TAA"
        metagenomic_sequence = f">meta_alpha\n{coding_sequence}\n>meta_beta\n{'ACGT' * 100}\n"
        metagenomic_args = source_variant(args, 3)
        metagenomic_id, metagenomic_token = submit(
            metagenomic_args,
            metagenomic_sequence,
            "metagenomic-smoke.fna",
            analysis_mode="metagenomic",
            include_crispr_arrays=False,
        )
        print(f"submitted real metagenomic job {metagenomic_id}", flush=True)
        metagenomic = wait_for_terminal(
            metagenomic_args, metagenomic_id, metagenomic_token, args.timeout
        )
        verify_metagenomic_job(
            metagenomic_args,
            metagenomic_token,
            metagenomic,
            ["meta_alpha", "meta_beta"],
        )

    cancel_sequence = ">cancel_probe\n" + "ACGT" * 50_000 + "\n"
    cancel_args = source_variant(args, 4)
    cancel_id, cancel_token = submit(
        cancel_args,
        cancel_sequence,
        "cancel-probe.fasta",
        analysis_mode="complete_genome",
        include_crispr_arrays=False,
    )
    status, _headers, payload = request(
        cancel_args,
        "DELETE",
        f"{API}/jobs/{cancel_id}",
        token=cancel_token,
        origin=args.origin,
    )
    cancelled = json_body(status, payload, {200}).get("job", {})
    if cancelled.get("status") not in {"running", "cancelled"}:
        raise RuntimeError("cancellation request returned an unexpected job state")
    cancelled = wait_for_terminal(cancel_args, cancel_id, cancel_token, 300)
    if cancelled.get("status") != "cancelled":
        raise RuntimeError("cancellation smoke did not reach cancelled state")

    overview = completed["summary"]["overview"]
    print(
        "E2E passed: "
        f"Cas proteins={overview.get('cas_protein_count')}, "
        f"cassettes={overview.get('cassette_count')}, "
        f"CRISPR arrays={overview.get('crispr_array_count')}; "
        "schema 5, mode-specific artifacts, CORS, authorization, and cancellation verified.",
        flush=True,
    )


if __name__ == "__main__":
    main()

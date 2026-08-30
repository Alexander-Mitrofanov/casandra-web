"""Reproduce the synthetic 100M-nt admission and worker capacity checks.

The probe never uses publication or benchmark data.  Run its stages as separate
processes so the worker measurement does not retain the admission allocator.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from casandra_web.api import create_app
from casandra_web.config import Settings
from casandra_web.db import Store
from casandra_web.models import JobSubmission
from casandra_web.service import JobService
from casandra_web.worker import Worker

CAS_ONLY_REQUEST_BYTES = 110_000_000
CAS_ONLY_BASES = 100_000_000
CAS_ONLY_RECORD_BASES = 100_000_000
CAS_ONLY_RECORDS = 10_000
ARRAY_REQUEST_BYTES = 4_500_000
ARRAY_BASES = 2_000_000
ARRAY_RECORDS = 20
PROTEIN_REQUEST_BYTES = 4_500_000
MODEL_BUNDLE_ID = "casandra-cas-only-cpu-bundle-v5-type-ii-architecture"
MODEL_MANIFEST_SHA256 = (
    "89657480e1135aec57f7e2b4a45fe5150f10fbdcbf80bf640e4325f7b921a071"
)


def _settings(data_root: Path, casandra: Path, worker_cpu: int) -> Settings:
    return Settings(
        data_root=data_root,
        database_path=data_root / "queue.sqlite3",
        token_pepper="local-synthetic-capacity-probe-only",
        cors_origins=("https://capacity.invalid",),
        casandra_command=(str(casandra),),
        identify_command=("/usr/bin/false",),
        identify_runner_config=None,
        max_request_bytes=CAS_ONLY_REQUEST_BYTES,
        max_total_bases=CAS_ONLY_BASES,
        max_record_bases=CAS_ONLY_RECORD_BASES,
        max_records=CAS_ONLY_RECORDS,
        max_array_request_bytes=ARRAY_REQUEST_BYTES,
        max_array_total_bases=ARRAY_BASES,
        max_array_records=ARRAY_RECORDS,
        max_protein_request_bytes=PROTEIN_REQUEST_BYTES,
        max_total_residues=2_000_000,
        max_protein_residues=100_000,
        max_protein_records=10_000,
        max_header_characters=200,
        max_queued_jobs=2,
        max_active_jobs=3,
        max_active_jobs_per_client=1,
        retention_seconds=86_400,
        worker_cpu=worker_cpu,
        stage_timeout_seconds=7_200,
        worker_poll_seconds=2,
        worker_heartbeat_seconds=15,
        worker_stale_seconds=90,
        max_attempts=2,
        max_log_bytes=2_000_000,
        max_retained_jobs=20,
        max_retained_input_bases=250_000_000,
        submission_window_seconds=3_600,
        max_submissions_per_window=3,
        min_free_bytes=20_000_000_000,
        min_free_inodes=100_000,
        max_job_storage_bytes=2_000_000_000,
        max_job_lifetime_seconds=28_800,
        casandra_bundle_id=MODEL_BUNDLE_ID,
        casandra_bundle_manifest_sha256=MODEL_MANIFEST_SHA256,
        casandra_program_version="0.3.0.dev0",
        casandra_schema_version=5,
        casandra_bundle_role="deployment_refit",
    )


def _new_data_root(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if path == Path(path.anchor):
        raise SystemExit("data root cannot be a filesystem root")
    if path.exists():
        raise SystemExit(f"refusing to reuse an existing data root: {path}")
    path.mkdir(parents=True, mode=0o700)
    return path


def _existing_data_root(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if path == Path(path.anchor) or not path.is_dir() or path.is_symlink():
        raise SystemExit(f"data root is unavailable: {path}")
    if not (path / "queue.sqlite3").is_file():
        raise SystemExit(f"queue database is unavailable under: {path}")
    return path


def _fasta_stats(path: Path) -> tuple[int, int]:
    records = 0
    bases = 0
    with path.open("rb") as handle:
        for line in handle:
            if line.startswith(b">"):
                records += 1
            else:
                bases += len(line.strip())
    return records, bases


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _assert_fixture(path: Path, expected_records: int, expected_bases: int) -> None:
    if not path.is_file() or path.is_symlink():
        raise SystemExit(f"FASTA fixture is unavailable: {path}")
    records, bases = _fasta_stats(path)
    if (records, bases) != (expected_records, expected_bases):
        raise SystemExit(
            "fixture dimensions differ from the requested probe: "
            f"got {records} records/{bases} bases"
        )


def generate(args: argparse.Namespace) -> None:
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite fixture: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    state = 1
    alphabet = b"ACGT"
    sequence = bytearray()
    for _ in range(args.bases_per_record):
        state = (1_103_515_245 * state + 12_345) & 0x7FFF_FFFF
        sequence.append(alphabet[(state >> 16) & 3])
    with output.open("xb") as handle:
        for record_number in range(1, args.records + 1):
            handle.write(f">synthetic_{record_number}\n".encode("ascii"))
            for offset in range(0, len(sequence), args.line_width):
                handle.write(sequence[offset : offset + args.line_width])
                handle.write(b"\n")
    digest = _sha256_file(output)
    print(
        json.dumps(
            {
                "path": str(output),
                "sha256": digest,
                "file_bytes": output.stat().st_size,
                "records": args.records,
                "bases": args.records * args.bases_per_record,
                "bases_per_record": args.bases_per_record,
                "line_width": args.line_width,
            },
            sort_keys=True,
        )
    )


async def _admit(args: argparse.Namespace) -> None:
    import httpx2 as httpx

    fasta = Path(args.fasta).expanduser().resolve()
    _assert_fixture(fasta, args.expected_records, args.expected_bases)
    data_root = _new_data_root(args.data_root)
    settings = _settings(data_root, Path(args.casandra).resolve(), args.worker_cpu)
    body = json.dumps(
        {
            "analysis_mode": "complete_genome",
            "sequence": fasta.read_text(encoding="ascii"),
            "filename": fasta.name,
            "include_crispr_arrays": False,
        },
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://capacity.invalid"
        ) as client,
    ):
        response = await client.post(
            "/casandra/api/v1/jobs",
            content=body,
            headers={"content-type": "application/json"},
        )
    payload = response.json()
    if response.status_code != 202:
        raise SystemExit(f"admission failed with HTTP {response.status_code}: {payload}")
    job = payload["job"]
    print(
        json.dumps(
            {
                "http_status": response.status_code,
                "json_body_bytes": len(body),
                "job_id": job["job_id"],
                "record_count": job["input"]["record_count"],
                "base_count": job["input"]["base_count"],
                "include_crispr_arrays": job["options"]["include_crispr_arrays"],
                "data_root": str(data_root),
            },
            sort_keys=True,
        )
    )


def admission(args: argparse.Namespace) -> None:
    asyncio.run(_admit(args))


def prepare_worker(args: argparse.Namespace) -> None:
    fasta = Path(args.fasta).expanduser().resolve()
    _assert_fixture(fasta, args.expected_records, args.expected_bases)
    data_root = _new_data_root(args.data_root)
    settings = _settings(data_root, Path(args.casandra).resolve(), args.worker_cpu)
    store = Store(settings)
    store.initialize()
    created = JobService(settings, store).submit(
        JobSubmission(
            analysis_mode="complete_genome",
            sequence=fasta.read_text(encoding="ascii"),
            filename=fasta.name,
            include_crispr_arrays=False,
        ),
        "192.0.2.100",
    )
    print(
        json.dumps(
            {
                "job_id": created.job.job_id,
                "status": created.job.status,
                "record_count": created.job.input.record_count,
                "base_count": created.job.input.base_count,
                "include_crispr_arrays": created.job.options.include_crispr_arrays,
                "worker_cpu": args.worker_cpu,
                "data_root": str(data_root),
            },
            sort_keys=True,
        )
    )


def _only_job_id(database: Path) -> str:
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        rows = connection.execute("SELECT job_id FROM jobs ORDER BY created_at").fetchall()
    if len(rows) != 1:
        raise SystemExit(f"expected exactly one prepared job, found {len(rows)}")
    return str(rows[0][0])


def _tree_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def run_worker(args: argparse.Namespace) -> None:
    data_root = _existing_data_root(args.data_root)
    casandra = Path(args.casandra).expanduser().resolve()
    if not casandra.is_file() or not os.access(casandra, os.X_OK):
        raise SystemExit(f"CasAndra executable is unavailable: {casandra}")
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[name] = str(args.worker_cpu)
    settings = _settings(data_root, casandra, args.worker_cpu)
    store = Store(settings)
    job_id = _only_job_id(settings.database_path)
    ran = Worker(settings, store=store, worker_id="synthetic-capacity-probe").run_once()
    job = store.get_job(job_id)
    if not ran or job is None:
        raise SystemExit("worker did not claim the prepared job")
    result = {
        "job_id": job_id,
        "status": job["status"],
        "phase": job["phase"],
        "record_count": job["record_count"],
        "base_count": job["base_count"],
        "include_crispr_arrays": bool(job["include_crispr_arrays"]),
        "worker_cpu": args.worker_cpu,
        "tree_bytes": _tree_bytes(data_root / "jobs" / job_id),
        "data_root": str(data_root),
    }
    print(json.dumps(result, sort_keys=True))
    if job["status"] != "completed":
        raise SystemExit(f"worker ended in status {job['status']}")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    subparsers = value.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="create deterministic FASTA")
    generate_parser.add_argument("--output", required=True)
    generate_parser.add_argument("--records", type=int, default=1_000)
    generate_parser.add_argument("--bases-per-record", type=int, default=100_000)
    generate_parser.add_argument("--line-width", type=int, default=80)
    generate_parser.set_defaults(handler=generate)

    def add_runtime_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--fasta", required=True)
        command.add_argument("--data-root", required=True)
        command.add_argument("--casandra", default="backend/.venv/bin/casandra")
        command.add_argument("--worker-cpu", type=int, default=12)
        command.add_argument("--expected-records", type=int, default=1_000)
        command.add_argument("--expected-bases", type=int, default=100_000_000)

    admission_parser = subparsers.add_parser("admission", help="exercise full ASGI admission")
    add_runtime_options(admission_parser)
    admission_parser.set_defaults(handler=admission)

    prepare_parser = subparsers.add_parser(
        "prepare-worker", help="admit one job in a process separate from the worker"
    )
    add_runtime_options(prepare_parser)
    prepare_parser.set_defaults(handler=prepare_worker)

    worker_parser = subparsers.add_parser("run-worker", help="execute the one prepared job")
    worker_parser.add_argument("--data-root", required=True)
    worker_parser.add_argument("--casandra", default="backend/.venv/bin/casandra")
    worker_parser.add_argument("--worker-cpu", type=int, default=12)
    worker_parser.set_defaults(handler=run_worker)
    return value


def main() -> None:
    args = parser().parse_args()
    if getattr(args, "records", 1) <= 0:
        raise SystemExit("records must be positive")
    if getattr(args, "bases_per_record", 1) <= 0:
        raise SystemExit("bases per record must be positive")
    if getattr(args, "line_width", 1) <= 0:
        raise SystemExit("line width must be positive")
    if getattr(args, "expected_records", 1) <= 0:
        raise SystemExit("expected records must be positive")
    if getattr(args, "expected_bases", 1) <= 0:
        raise SystemExit("expected bases must be positive")
    if not 1 <= getattr(args, "worker_cpu", 12) <= 16:
        raise SystemExit("worker CPU must be between 1 and 16")
    args.handler(args)


if __name__ == "__main__":
    main()

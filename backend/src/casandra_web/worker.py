"""Single-concurrency scientific worker."""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path

from .config import Settings
from .db import CancellationPending, ClaimedJob, LeaseError, Store
from .exports import ExportError, build_result_exports
from .security import new_job_id
from .service import JobService
from .summary import (
    SummaryError,
    build_cassette_summary,
    build_protein_summary,
    build_summary,
)

LOGGER = logging.getLogger("casandra_web.worker")


class JobCancelled(RuntimeError):
    pass


class WorkerStopping(RuntimeError):
    pass


class StageFailure(RuntimeError):
    def __init__(self, stage: str, reason: str):
        self.stage = stage
        self.reason = reason
        super().__init__(f"{stage}: {reason}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _resolve_program(command: tuple[str, ...]) -> None:
    program = command[0]
    if "/" in program or "\\" in program:
        path = Path(program)
        if not path.is_file() or not os.access(path, os.X_OK):
            raise FileNotFoundError(f"configured executable is unavailable: {path.name}")
    elif shutil.which(program) is None:
        raise FileNotFoundError(f"configured executable is unavailable: {program}")


def _terminate(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait(timeout=10)


def _runtime_output(command: list[str], label: str, *, timeout: int = 300) -> str:
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"{label} runtime preflight could not run") from error
    if result.returncode != 0:
        raise RuntimeError(f"{label} runtime preflight failed")
    return result.stdout.strip()


def _tree_size_exceeds(root: Path, maximum: int) -> bool:
    total = 0
    pending = [root]
    entries = 0
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as iterator:
            for entry in iterator:
                entries += 1
                if entries > 200_000:
                    return True
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                    if total > maximum:
                        return True
    return False


class Worker:
    def __init__(
        self,
        settings: Settings,
        *,
        store: Store | None = None,
        worker_id: str | None = None,
    ):
        self.settings = settings
        self.store = store or Store(settings)
        self.service = JobService(settings, self.store)
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.stop_event = threading.Event()

    def validate_runtime(self) -> None:
        _resolve_program(self.settings.casandra_command)
        _resolve_program(self.settings.identify_command)
        if self.settings.identify_runner_config is not None:
            path = self.settings.identify_runner_config
            if not path.is_absolute() or not path.is_file() or path.is_symlink():
                raise FileNotFoundError("the configured CRISPRidentify runner file is unavailable")
        if not self.settings.preflight_scientific_runtime:
            return
        model_inspection = _runtime_output(
            [*self.settings.casandra_command, "inspect-model"], "CasAndra model"
        )
        try:
            model = json.loads(model_inspection)
        except json.JSONDecodeError as error:
            raise RuntimeError("CasAndra model preflight returned invalid JSON") from error
        if (
            not isinstance(model, dict)
            or not model.get("bundle_id")
            or model.get("integrity") != "verified"
            or model.get("cpu_only") is not True
            or model.get("offline_inference") is not True
        ):
            raise RuntimeError("CasAndra model preflight did not verify the deployment bundle")
        if (
            self.settings.casandra_bundle_id is not None
            and model.get("bundle_id") != self.settings.casandra_bundle_id
        ):
            raise RuntimeError("CasAndra model bundle does not match deployment policy")
        if (
            self.settings.casandra_bundle_role is not None
            and model.get("bundle_role") != self.settings.casandra_bundle_role
        ):
            raise RuntimeError("CasAndra model role does not match deployment policy")
        expected_version = self.settings.casandra_expected_version
        if expected_version is None and self.settings.casandra_program_version is not None:
            expected_version = f"casandra {self.settings.casandra_program_version}"
        if expected_version:
            actual = _runtime_output(
                [*self.settings.casandra_command, "--version"], "CasAndra version", timeout=30
            )
            if actual != expected_version:
                raise RuntimeError("CasAndra runtime version does not match deployment policy")
        if self.settings.integration_expected_version:
            actual = _runtime_output(
                [*self.settings.identify_command, "--version"],
                "Integration version",
                timeout=30,
            )
            if actual != self.settings.integration_expected_version:
                raise RuntimeError("Integration runtime version does not match deployment policy")
        version_path = self.settings.crispridentify_version_file
        expected_identify = self.settings.crispridentify_expected_version
        if version_path is None or expected_identify is None:
            raise RuntimeError("CRISPRidentify version preflight is not configured")
        if not version_path.is_file() or version_path.is_symlink():
            raise RuntimeError("CRISPRidentify version file is unavailable")
        try:
            actual_identify = version_path.read_text(encoding="ascii").strip()
        except (OSError, UnicodeError) as error:
            raise RuntimeError("CRISPRidentify version file could not be read") from error
        if actual_identify != expected_identify:
            raise RuntimeError("CRISPRidentify runtime version does not match deployment policy")

    def run_once(self) -> bool:
        self.store.heartbeat_worker(self.worker_id)
        claimed = self.store.claim_next(self.worker_id)
        if claimed is None:
            return False
        try:
            self._execute(claimed)
        except (JobCancelled, CancellationPending):
            self.store.mark_cancelled(claimed)
        except WorkerStopping:
            try:
                self.store.release_after_shutdown(claimed)
            except LeaseError:
                LOGGER.warning("job %s could not be released during shutdown", claimed.job_id)
        except StageFailure as error:
            LOGGER.warning("job %s failed in %s: %s", claimed.job_id, error.stage, error.reason)
            self.store.fail(
                claimed,
                f"{error.stage}_failed",
                f"The {error.stage} stage could not complete for this input.",
            )
        except LeaseError:
            LOGGER.warning("lease lost for job %s", claimed.job_id)
        except (SummaryError, ExportError) as error:
            LOGGER.warning("job %s result indexing failed: %s", claimed.job_id, error)
            self.store.fail(
                claimed,
                "result_validation_failed",
                "The scientific tools finished, but their outputs did not pass result validation.",
            )
        except Exception:
            LOGGER.exception("unexpected worker failure for job %s", claimed.job_id)
            self.store.fail(
                claimed,
                "internal_worker_error",
                "The analysis worker encountered an internal error.",
            )
        finally:
            self.store.heartbeat_worker(self.worker_id)
        return True

    def _execute(self, claimed: ClaimedJob) -> None:
        job = self.store.get_job(claimed.job_id)
        if job is None:
            raise LeaseError("job disappeared")
        root = self.service.job_root(claimed.job_id)
        result_root = root / "output" / f"attempt-{claimed.attempt:03d}-{uuid.uuid4().hex[:12]}"
        result_root.mkdir(mode=0o700, exist_ok=False)
        logs = result_root / "private-logs"
        logs.mkdir(mode=0o700)
        input_path = self.service.analysis_input_path(claimed.job_id, claimed.analysis_mode)

        self._checkpoint(claimed)
        self.store.set_phase(claimed, "casandra")
        casandra_output = result_root / "casandra"
        if claimed.analysis_mode in {"complete_genome", "metagenomic"}:
            casandra_command = [
                *self.settings.casandra_command,
                "predict-genome",
                "--genome",
                str(input_path),
                "--output",
                str(casandra_output),
                "--gene-mode",
                claimed.gene_mode,
                "--translation-table",
                "11",
                "--threads",
                str(self.settings.worker_cpu),
            ]
        elif claimed.analysis_mode == "annotate_cas_genes":
            casandra_command = [
                *self.settings.casandra_command,
                "annotate-proteins",
                "--input",
                str(input_path),
                "--output",
                str(casandra_output),
                "--threads",
                str(self.settings.worker_cpu),
            ]
        elif claimed.analysis_mode == "classify_cassette":
            casandra_command = [
                *self.settings.casandra_command,
                "classify-cassette",
                "--input",
                str(input_path),
                "--output",
                str(casandra_output),
                "--threads",
                str(self.settings.worker_cpu),
            ]
        else:
            raise StageFailure("casandra", "unsupported analysis mode")
        self._run_stage("casandra", casandra_command, logs, claimed)

        if claimed.include_crispr_arrays:
            self.store.set_phase(claimed, "crispridentify")
            identify_output = result_root / "identify"
            identify_command = [
                *self.settings.identify_command,
                "run",
                str(self.service.records_path(claimed.job_id)),
                str(identify_output),
                "--tools",
                "identify",
                "--categories",
                "Bona-fide",
                "Possible",
                "--cpu",
                str(self.settings.worker_cpu),
                "--identify-folder-jobs",
                str(min(self.settings.worker_cpu, int(job["record_count"]))),
                "--stage-timeout",
                str(
                    self.settings.stage_timeout_seconds
                    - min(60, max(1, self.settings.stage_timeout_seconds // 3))
                ),
            ]
            if self.settings.identify_runner_config is not None:
                identify_command.extend(
                    ["--runner-config", str(self.settings.identify_runner_config)]
                )
            self._run_stage("crispridentify", identify_command, logs, claimed)

        self.store.set_phase(claimed, "indexing")
        self._checkpoint(claimed)
        complete_features: dict[str, list[dict[str, object]]] = {}
        if claimed.analysis_mode in {"complete_genome", "metagenomic"}:
            summary, complete_features = build_summary(
                root,
                result_root,
                requested_gene_mode=claimed.gene_mode,
                analysis_mode=claimed.analysis_mode,
                include_crispr_arrays=claimed.include_crispr_arrays,
            )
        elif claimed.analysis_mode == "annotate_cas_genes":
            summary = build_protein_summary(root, result_root)
        else:
            summary = build_cassette_summary(root, result_root)
        summary_path = result_root / "result-summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.chmod(summary_path, 0o600)
        if claimed.include_crispr_arrays:
            arrays_path = result_root / "crispr-arrays.json"
            arrays_path.write_text(
                json.dumps(
                    {
                        "schema_version": summary["schema_version"],
                        "coordinates": "1-based-end-inclusive-source-forward",
                        "arrays": complete_features.get("crispr_arrays", []),
                    },
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n",
                encoding="utf-8",
            )
            os.chmod(arrays_path, 0o600)

        build_result_exports(
            root,
            result_root,
            analysis_mode=claimed.analysis_mode,
            summary=summary,
            validated_features=complete_features,
        )

        self.store.set_phase(claimed, "packaging")
        if _tree_size_exceeds(result_root, self.settings.max_job_storage_bytes):
            raise StageFailure("packaging", "job output exceeded the configured storage limit")
        artifacts = self._package_artifacts(claimed, root, result_root)
        if _tree_size_exceeds(result_root, self.settings.max_job_storage_bytes):
            raise StageFailure("packaging", "job output exceeded the configured storage limit")
        self._checkpoint(claimed)
        self.store.complete(claimed, summary, artifacts)

    def _run_stage(
        self,
        stage: str,
        command: list[str],
        logs: Path,
        claimed: ClaimedJob,
    ) -> None:
        stdout_path = logs / f"{stage}.stdout.log"
        stderr_path = logs / f"{stage}.stderr.log"
        deadline = time.monotonic() + self.settings.stage_timeout_seconds
        next_renewal = time.monotonic() + self.settings.worker_heartbeat_seconds
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            os.chmod(stdout_path, 0o600)
            os.chmod(stderr_path, 0o600)
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    start_new_session=True,
                    close_fds=True,
                )
            except OSError as error:
                raise StageFailure(stage, "configured process could not start") from error
            while process.poll() is None:
                if self.stop_event.wait(0.25):
                    _terminate(process)
                    raise WorkerStopping()
                try:
                    now = time.monotonic()
                    renew = now >= next_renewal
                    self._checkpoint(claimed, renew=renew)
                    if renew:
                        if _tree_size_exceeds(logs.parent, self.settings.max_job_storage_bytes):
                            _terminate(process)
                            raise StageFailure(
                                stage, "job output exceeded the configured storage limit"
                            )
                        next_renewal = now + self.settings.worker_heartbeat_seconds
                except BaseException:
                    _terminate(process)
                    raise
                if time.monotonic() >= deadline:
                    _terminate(process)
                    raise StageFailure(stage, "time limit exceeded")
                try:
                    if (
                        stdout_path.stat().st_size > self.settings.max_log_bytes
                        or stderr_path.stat().st_size > self.settings.max_log_bytes
                    ):
                        _terminate(process)
                        raise StageFailure(stage, "log output exceeded the configured limit")
                except OSError as error:
                    _terminate(process)
                    raise StageFailure(stage, "log output could not be inspected") from error
            if process.returncode != 0:
                raise StageFailure(stage, f"process exited with status {process.returncode}")

    def _checkpoint(self, claimed: ClaimedJob, *, renew: bool = True) -> None:
        if self.store.cancellation_requested(claimed):
            raise JobCancelled()
        if renew:
            self.store.renew_lease(claimed)
            self.store.heartbeat_worker(self.worker_id)

    def _package_artifacts(
        self, claimed: ClaimedJob, job_root: Path, result_root: Path
    ) -> list[dict[str, object]]:
        relative_files = [Path("result-summary.json")]
        relative_files.extend(
            [
                Path("exports/casandra-results.json"),
                Path("exports/casandra-results.csv"),
            ]
        )
        if claimed.analysis_mode in {"complete_genome", "metagenomic"}:
            relative_files.extend(
                [
                    Path("exports/cas-proteins.faa"),
                    Path("exports/cas-coding-sequences.fna"),
                    Path("casandra/cas_proteins.tsv"),
                    Path("casandra/cassettes.tsv"),
                    Path("casandra/casandra.gff3"),
                    Path("casandra/run.json"),
                    Path("casandra/manifest.json"),
                ]
            )
        elif claimed.analysis_mode == "annotate_cas_genes":
            relative_files.extend(
                [
                    Path("exports/all-proteins.faa"),
                    Path("exports/cas-proteins.faa"),
                    Path("casandra/protein_predictions.jsonl"),
                    Path("casandra/run.json"),
                    Path("casandra/manifest.json"),
                ]
            )
        elif claimed.analysis_mode == "classify_cassette":
            relative_files.extend(
                [
                    Path("exports/cassette-proteins.faa"),
                    Path("exports/cassette-cas-proteins.faa"),
                    Path("casandra/proteins.jsonl"),
                    Path("casandra/cassette.json"),
                    Path("casandra/run.json"),
                    Path("casandra/manifest.json"),
                ]
            )
        if claimed.include_crispr_arrays:
            relative_files.extend(
                [
                    Path("exports/crispr-arrays.fna"),
                    Path("exports/crispr-components.fna"),
                    Path("crispr-arrays.json"),
                    Path("identify/integration_result.json"),
                    Path("identify/adapter/manifest.json"),
                ]
            )
        safe_files: list[Path] = []
        for relative in relative_files:
            path = result_root / relative
            if path.is_file() and not path.is_symlink():
                safe_files.append(path)
        archive = result_root / "casandra-results.zip"
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in safe_files:
                bundle.write(path, arcname=str(path.relative_to(result_root)))
        os.chmod(archive, 0o600)
        safe_files.append(archive)

        artifacts: list[dict[str, object]] = []
        for path in safe_files:
            relative_to_job = path.relative_to(job_root)
            relative_to_result = path.relative_to(result_root)
            display_names = {
                "casandra/run.json": "casandra-run.json",
                "casandra/manifest.json": "casandra-manifest.json",
                "casandra/protein_predictions.jsonl": "protein-predictions.jsonl",
                "casandra/proteins.jsonl": "protein-predictions.jsonl",
                "casandra/cassette.json": "cassette-classification.json",
                "identify/integration_result.json": "crispridentify-run.json",
                "identify/adapter/manifest.json": "crispridentify-adapter-manifest.json",
            }
            display_name = display_names.get(str(relative_to_result), path.name)
            media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if path.suffix == ".json":
                media_type = "application/json"
            elif path.suffix == ".jsonl":
                media_type = "application/x-ndjson"
            elif path.suffix == ".tsv":
                media_type = "text/tab-separated-values"
            elif path.suffix == ".csv":
                media_type = "text/csv"
            elif path.suffix in {".faa", ".fna", ".fasta"}:
                media_type = "text/x-fasta"
            elif path.suffix == ".gff3":
                media_type = "text/plain"
            elif path.suffix == ".zip":
                media_type = "application/zip"
            artifacts.append(
                {
                    "artifact_id": new_job_id(),
                    "name": display_name,
                    "relative_path": str(relative_to_job),
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                    "media_type": media_type,
                }
            )
        return artifacts

    def run_forever(self) -> None:
        self.validate_runtime()
        while not self.stop_event.is_set():
            worked = self.run_once()
            if not worked:
                self.stop_event.wait(self.settings.worker_poll_seconds)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    settings = Settings.from_env()
    store = Store(settings)
    store.initialize()
    worker = Worker(settings, store=store)

    def stop(_signum, _frame) -> None:
        worker.stop_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    worker.run_forever()


if __name__ == "__main__":
    main()

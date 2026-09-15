"""Switch the standalone service's model after draining its existing queue.

Run as root: python -m casandra_web.model_switch MODEL_NAME
The --check option validates a candidate without changing services or files.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shlex
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .config import Settings
from .model_registry import validate_name
from .worker import Worker

SELECTION = Path("/etc/casandra-web-model.env")
BASE_ENV = Path("/etc/casandra-web.env")
SWITCH_LOCK = Path("/run/lock/casandra-web-model-switch.lock")
API = "casandra-web-api.service"
WORKER = "casandra-web-worker.service"


def read_environment(path: Path) -> dict[str, str]:
    """Read the literal assignments used by our systemd environment templates."""
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, raw = line.partition("=")
        if not separator or not name.replace("_", "").isalnum():
            raise ValueError("invalid service environment assignment")
        # Unquoted internal whitespace is literal in systemd EnvironmentFile.
        result[name] = " ".join(shlex.split(raw)) if raw[:1] in {"'", '"'} else raw
    return result


def candidate_settings(name: str, registry: str | None) -> Settings:
    validate_name(name)
    values = read_environment(BASE_ENV)
    if SELECTION.exists():
        selected = read_environment(SELECTION)
        if set(selected) - {"CASANDRA_WEB_MODEL_NAME", "CASANDRA_WEB_MODEL_REGISTRY"}:
            raise ValueError("model selection file contains unrelated service settings")
        values.update(selected)
    values["CASANDRA_WEB_MODEL_NAME"] = name
    if registry is not None:
        values["CASANDRA_WEB_MODEL_REGISTRY"] = registry
    previous = os.environ.copy()
    try:
        for key in list(os.environ):
            if key.startswith("CASANDRA_WEB_"):
                del os.environ[key]
        os.environ.update(values)
        return Settings.from_env()
    finally:
        os.environ.clear()
        os.environ.update(previous)


def atomic_selection(path: Path, content: bytes | None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".casandra-model-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class StandaloneServices:
    def __init__(self, database: Path, drain_timeout: float):
        self.database = database
        self.drain_timeout = drain_timeout

    @staticmethod
    def control(action: str, unit: str) -> None:
        subprocess.run(["/usr/bin/systemctl", action, unit], check=True, timeout=120)

    def assert_switchable(self) -> None:
        for unit in (API, WORKER):
            self.control("is-active", unit)
            result = subprocess.run(["/usr/bin/systemctl", "cat", unit], check=True,
                                    capture_output=True, text=True, timeout=30)
            if f"EnvironmentFile=-{SELECTION}" not in result.stdout.splitlines():
                raise RuntimeError("install the model-selection systemd units before switching")

    def _query(self, query: str, parameters: tuple = ()):
        with sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True, timeout=5) as db:
            return db.execute(query, parameters).fetchone()[0]

    def drain(self) -> None:
        deadline = time.monotonic() + self.drain_timeout
        while self._query("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')"):
            if time.monotonic() >= deadline:
                raise TimeoutError("queue did not drain; keeping the previous model")
            time.sleep(1)

    def start_worker(self) -> None:
        started = time.time()
        self.control("start", WORKER)
        deadline = time.monotonic() + 300
        while not self._query(
            "SELECT COUNT(*) FROM workers WHERE status='ok' AND heartbeat_at>=?", (started,)
        ):
            if time.monotonic() >= deadline:
                raise TimeoutError("selected worker did not complete startup and heartbeat")
            time.sleep(1)

    def start_api(self) -> None:
        self.control("start", API)
        values = read_environment(BASE_ENV)
        port = int(values.get("CASANDRA_WEB_PORT", "8010"))
        url = f"http://127.0.0.1:{port}/casandra/api/v1/health"
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                with urlopen(url, timeout=2) as response:
                    if json.load(response).get("status") == "ok":
                        return
            except (OSError, URLError, ValueError):
                pass
            time.sleep(1)
        raise TimeoutError("API did not become healthy after model switch")


def switch_selection(path: Path, content: bytes, services: StandaloneServices) -> None:
    """No worker is stopped until its queue is empty; failed startup rolls back."""
    old = path.read_bytes() if path.exists() else None
    services.assert_switchable()
    worker_stopped = False
    selection_changed = False
    try:
        services.control("stop", API)
        print("Waiting for queued and running jobs to finish…", flush=True)
        services.drain()
        worker_stopped = True
        services.control("stop", WORKER)
        atomic_selection(path, content)
        selection_changed = True
        services.start_worker()
        services.start_api()
    except BaseException:
        # Stop admissions before restoring; even a partly started API may have
        # accepted work. Finish that work under the selected model first.
        services.control("stop", API)
        if selection_changed:
            services.drain()
            services.control("stop", WORKER)
            atomic_selection(path, old)
        if worker_stopped:
            services.start_worker()
        services.start_api()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("--registry", default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--drain-timeout", type=int, default=14_400)
    args = parser.parse_args()
    if args.drain_timeout <= 0:
        parser.error("--drain-timeout must be positive")
    configured = candidate_settings(args.name, args.registry)
    check_command = ["/usr/sbin/runuser", "-u", "casandrasvc", "--", sys.executable,
                     "-I", "-B", "-m", "casandra_web.model_switch", args.name, "--check"]
    if args.registry is not None:
        check_command.extend(["--registry", args.registry])
    if args.check:
        if os.geteuid() == 0:
            subprocess.run(check_command, check=True, timeout=600)
            return
        Worker(replace(configured, preflight_scientific_runtime=True)).validate_runtime()
        print(f"Verified model: {configured.model_name}")
        return
    if os.geteuid() != 0:
        parser.error("model switching must run as root; --check is read-only")
    if SELECTION.is_symlink():
        parser.error("model selection must be an operator-owned regular file")

    def interrupted(_signum, _frame):
        raise InterruptedError("model switching interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    with SWITCH_LOCK.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Deserialize the operator's candidate as the service user, never as root.
        subprocess.run(check_command, check=True, timeout=600)
        registry = args.registry
        if registry is None and SELECTION.exists():
            registry = read_environment(SELECTION).get("CASANDRA_WEB_MODEL_REGISTRY")
        if registry is None:
            registry = read_environment(BASE_ENV).get("CASANDRA_WEB_MODEL_REGISTRY")
        lines = [f"CASANDRA_WEB_MODEL_NAME={args.name}"]
        if registry:
            if not Path(registry).is_absolute() or any(char.isspace() for char in registry):
                parser.error("registry path must be absolute and contain no whitespace")
            lines.append(f"CASANDRA_WEB_MODEL_REGISTRY={registry}")
        switch_selection(SELECTION, ("\n".join(lines) + "\n").encode(),
                         StandaloneServices(configured.database_path, args.drain_timeout))
    print(f"Active backend model: {args.name}")


if __name__ == "__main__":
    main()

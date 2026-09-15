import subprocess
from pathlib import Path

import pytest

import casandra_web.model_switch as switch_module
from casandra_web.model_switch import StandaloneServices, read_environment, switch_selection


class Services:
    def __init__(self, *, fail=None):
        self.events = []
        self.fail = fail
        self.worker_starts = 0

    def assert_switchable(self):
        self.events.append("check-units")

    def control(self, action, unit):
        self.events.append((action, unit))

    def drain(self):
        self.events.append("drain")
        if self.fail == "drain":
            raise TimeoutError("pending job")

    def start_worker(self):
        self.worker_starts += 1
        self.events.append("start-worker-verified")
        if self.fail == "worker" and self.worker_starts == 1:
            raise RuntimeError("candidate failed startup")

    def start_api(self):
        self.events.append("start-api-healthy")
        if self.fail == "api" and self.worker_starts == 1:
            raise RuntimeError("candidate API failed startup")


def test_switch_drains_before_stopping_worker_and_publishes_atomically(tmp_path, monkeypatch):
    path = tmp_path / "selection.env"
    path.write_bytes(b"CASANDRA_WEB_MODEL_NAME=default\n")
    services = Services()
    atomic = switch_module.atomic_selection

    def publish(target, content):
        services.events.append("write-selection")
        atomic(target, content)

    monkeypatch.setattr(switch_module, "atomic_selection", publish)
    switch_selection(path, b"CASANDRA_WEB_MODEL_NAME=kira\n", services)
    assert path.read_bytes() == b"CASANDRA_WEB_MODEL_NAME=kira\n"
    assert services.events == ["check-units", ("stop", switch_module.API), "drain",
                               ("stop", switch_module.WORKER), "write-selection",
                               "start-worker-verified", "start-api-healthy"]


def test_drain_timeout_preserves_running_worker_and_original_selection(tmp_path):
    path = tmp_path / "selection.env"
    old = b"CASANDRA_WEB_MODEL_NAME=default\n"
    path.write_bytes(old)
    services = Services(fail="drain")
    with pytest.raises(TimeoutError):
        switch_selection(path, b"CASANDRA_WEB_MODEL_NAME=kira\n", services)
    assert path.read_bytes() == old
    assert ("stop", switch_module.WORKER) not in services.events
    assert "start-worker-verified" not in services.events
    assert services.events[-1] == "start-api-healthy"


@pytest.mark.parametrize("failure", ["worker", "api"])
@pytest.mark.parametrize("old", [None, b"CASANDRA_WEB_MODEL_NAME=default\n"])
def test_failed_startup_restores_old_selection_and_services(tmp_path, old, failure):
    path = tmp_path / "selection.env"
    if old is not None:
        path.write_bytes(old)
    services = Services(fail=failure)
    with pytest.raises(RuntimeError, match="failed startup"):
        switch_selection(path, b"CASANDRA_WEB_MODEL_NAME=kira\n", services)
    assert (path.read_bytes() if path.exists() else None) == old
    assert services.worker_starts == 2
    assert services.events[-2:] == ["start-worker-verified", "start-api-healthy"]
    assert services.events.count("drain") == 2


def test_systemd_environment_parser_handles_quoted_commands_and_literal_spaces():
    root = Path(__file__).resolve().parents[2]
    values = read_environment(root / "deploy/casandra-web.env.example")
    assert values["CASANDRA_WEB_CASANDRA_EXPECTED_VERSION"] == "casandra 0.3.0.dev0"
    assert values["CASANDRA_WEB_CASANDRA_COMMAND"] == (
        '["/srv/casandra/releases/backend/current/venv/bin/casandra"]'
    )


def test_drain_observes_active_jobs_without_claiming_or_cancelling(settings):
    from casandra_web.db import Store
    from casandra_web.models import JobSubmission
    from casandra_web.service import JobService

    store = Store(settings)
    store.initialize()
    service = JobService(settings, store)
    created = service.submit(JobSubmission(analysis_mode="annotate_cas_genes",
        sequence=">query\nMTESTMTESTMTESTMTESTMTESTMTESTMTEST\n"), "192.0.2.1")
    control = StandaloneServices(settings.database_path, drain_timeout=0)
    with pytest.raises(TimeoutError):
        control.drain()
    row = store.get_job(created.job.job_id)
    assert row["status"] == "queued"
    assert row["attempt"] == 0
    claimed = store.claim_next("existing-worker")
    with pytest.raises(TimeoutError):
        control.drain()
    assert store.get_job(created.job.job_id)["worker_id"] == "existing-worker"
    assert not store.cancellation_requested(claimed)
    store.complete(claimed, {}, [])
    control.drain()


def test_candidate_preflight_failure_never_stops_services_or_changes_selection(
    settings, tmp_path, monkeypatch,
):
    path = tmp_path / "selection.env"
    path.write_bytes(b"CASANDRA_WEB_MODEL_NAME=default\n")
    monkeypatch.setattr(switch_module, "SELECTION", path)
    monkeypatch.setattr(switch_module, "SWITCH_LOCK", tmp_path / "switch.lock")
    monkeypatch.setattr(switch_module, "candidate_settings", lambda *args: settings)
    monkeypatch.setattr(switch_module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(switch_module.signal, "signal", lambda *args: None)
    monkeypatch.setattr(switch_module.sys, "argv", ["model-switch", "kira"])
    calls = []

    def fail_check(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(switch_module.subprocess, "run", fail_check)
    with pytest.raises(subprocess.CalledProcessError):
        switch_module.main()
    assert len(calls) == 1
    assert calls[0][:4] == ["/usr/sbin/runuser", "-u", "casandrasvc", "--"]
    assert calls[0][-1] == "--check"
    assert path.read_bytes() == b"CASANDRA_WEB_MODEL_NAME=default\n"

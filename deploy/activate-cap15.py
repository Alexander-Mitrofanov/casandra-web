#!/usr/bin/env python3
"""Stage, verify and activate the pinned cap15 paired release on the existing VM.

Usage: sudo python3 activate-cap15.py PACKAGE_DIRECTORY [--stage-only | --rollback]
The package manifest pins every payload. Existing jobs and the old release survive.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

API = "casandra-web-api.service"
WORKER = "casandra-web-worker.service"
CLEANUP = "casandra-web-cleanup.timer"
CURRENT = Path("/srv/casandra/releases/backend/current")
BASE = Path("/etc/casandra-web.env")
SELECTION = Path("/etc/casandra-web-model.env")
DB = Path("/srv/casandra/jobs/queue.sqlite3")
BUNDLE_ID = "casandra-full361-v3-cap15-2026-09-20-v1"
PIN = "966c4522d38585db6c3dbca14566aa25d520b7c165f487abe5f35845441eb1b3"
OLD_PIN = "4e527cf17c56b9967a6e1c7664238196df9a0c0da76b9d7f7f99c55cc9a9ec41"
OLD_WHEELS = Path("/srv/casandra/staging/c73be92c23c44815d51c961995018dfe796518bf0ace68b05096dd030947d607/wheelhouse")


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def version():
    with urlopen("http://127.0.0.1:8010/casandra/api/v1/version", timeout=5) as response:
        return json.load(response)


def query(sql):
    with sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True, timeout=10) as connection:
        return connection.execute(sql).fetchall()


def drain():
    deadline = time.monotonic() + 28800
    while query("SELECT count(*) FROM jobs WHERE status IN ('queued','running')")[0][0]:
        if time.monotonic() > deadline:
            raise TimeoutError("Existing jobs did not drain")
        time.sleep(2)


def atomic(path, content):
    temporary = path.with_name("." + path.name + ".cap15")
    temporary.write_bytes(content)
    if path.exists():
        stat = path.stat()
        os.chown(temporary, stat.st_uid, stat.st_gid)
        os.chmod(temporary, stat.st_mode & 0o777)
    else:
        os.chmod(temporary, 0o644)
    temporary.replace(path)


def select_release(path):
    temporary = CURRENT.with_name(".cap15-current")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(path)
    temporary.replace(CURRENT)


def wait_ready(pin):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            current = version()
            with urlopen("http://127.0.0.1:8010/casandra/api/v1/health", timeout=5) as response:
                healthy = json.load(response).get("status") == "ok"
            if healthy and current.get("casandra_bundle_manifest_sha256") == pin:
                run("systemctl", "is-active", "--quiet", API, WORKER)
                return current
        except (OSError, ValueError, subprocess.CalledProcessError):
            pass
        time.sleep(2)
    raise RuntimeError("The paired release did not become healthy")


def restore(backup):
    run("systemctl", "stop", API)
    drain()
    run("systemctl", "stop", WORKER)
    atomic(BASE, (backup / "base.env").read_bytes())
    atomic(SELECTION, (backup / "selection.env").read_bytes())
    select_release(Path((backup / "previous-release.txt").read_text().strip()))
    run("systemctl", "reset-failed", WORKER, API)
    run("systemctl", "start", WORKER, API, CLEANUP)
    return wait_ready(OLD_PIN)


def stage(package, manifest, release):
    if release.exists():
        raise RuntimeError("Release directory exists; inspect before repeating staging")
    for relative, record in manifest["files"].items():
        path = package / relative
        if (not path.resolve().is_relative_to(package) or path.is_symlink()
                or not path.is_file() or path.stat().st_size != record["bytes"]
                or digest(path) != record["sha256"]):
            raise RuntimeError(f"Package integrity failed: {relative}")
    wheel_manifest = OLD_WHEELS.parent / "SHA256SUMS"
    if digest(wheel_manifest) != OLD_WHEELS.parent.name:
        raise RuntimeError("Existing offline dependency wheelhouse is not attested")
    run("sha256sum", "--check", "--strict", "SHA256SUMS", cwd=OLD_WHEELS.parent,
        stdout=subprocess.DEVNULL)
    release.mkdir()
    shutil.copytree(package / "source", release / "source")
    shutil.copytree(package / "model", release / "model")
    run("python3", "-m", "venv", release / "venv")
    python = release / "venv/bin/python"
    run(python, "-I", "-B", "-m", "pip", "--isolated", "install", "--no-index",
        "--no-cache-dir", "--no-compile", "--find-links", OLD_WHEELS,
        "--find-links", package / "wheels", "-r", package / "scientific-requirements.txt",
        package / "wheels/casandra_web-0.2.0.dev0-py3-none-any.whl",
        package / "wheels/CasAndra-0.3.0.dev2-py3-none-any.whl")
    run(python, "-I", "-B", "-m", "pip", "--isolated", "check")
    run(python, "-I", "-B", "-m", "casandra_web.model_registry",
        "--registry", release / "registry.json", "--name", BUNDLE_ID,
        "--bundle", release / "model", "--program-version", "0.3.0.dev2",
        "--result-schema-version", "5", stdout=subprocess.DEVNULL)
    (release / "release.env").write_text(f"CASANDRA_WEB_RELEASE_ID={manifest['release_id']}\n")
    # Preflight as the service account using the real detector configuration and new CLI.
    preflight = (
        "import os,sys; from casandra_web.model_switch import read_environment; "
        "from casandra_web.config import Settings; from casandra_web.worker import Worker; "
        "os.environ.update(read_environment(__import__('pathlib').Path('/etc/casandra-web.env'))); "
        "os.environ.update(CASANDRA_WEB_MODEL_NAME=sys.argv[1],CASANDRA_WEB_MODEL_REGISTRY=sys.argv[2],"
        "CASANDRA_WEB_CASANDRA_EXPECTED_VERSION='casandra 0.3.0.dev2',"
        "CASANDRA_WEB_CASANDRA_COMMAND=__import__('json').dumps([sys.argv[3]])); "
        "Worker(Settings.from_env()).validate_runtime(); print('Paired runtime/model/detector preflight passed')"
    )
    run("chown", "-R", "root:root", release)
    run("chmod", "-R", "a+rX,go-w", release)
    run("runuser", "-u", "casandrasvc", "--", python, "-I", "-B", "-c", preflight,
        BUNDLE_ID, release / "registry.json", release / "venv/bin/casandra")
    installed = json.loads(subprocess.check_output(
        [str(python), "-I", "-B", "-m", "pip", "list", "--format=json"], text=True))
    site = Path(subprocess.check_output([str(python), "-I", "-B", "-c",
        "import sysconfig;print(sysconfig.get_path('purelib'))"], text=True).strip())
    source_files = list((release / "source/src/casandra_web").glob("*.py"))
    for source in source_files:
        assert digest(source) == digest(site / "casandra_web" / source.name)
    save(package / "staged.json", {"release": str(release), "manifest_sha256": digest(package / "package.json"),
        "installed": installed, "backend_source_files_verified": len(source_files)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--stage-only", action="store_true")
    group.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0 or socket.gethostname() != "casandra-web-server":
        raise SystemExit("Run as root on the existing casandra-web-server VM")
    package = args.package.resolve(strict=True)
    lock = open("/run/lock/casandra-web-model-switch.lock", "a")  # noqa: SIM115 -- hold until process exit
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    backup = package / "rollback"
    if args.rollback:
        save(package / "rollback-result.json", restore(backup))
        return
    manifest = json.loads((package / "package.json").read_text())
    assert manifest["bundle_manifest_sha256"] == PIN and manifest["bundle_id"] == BUNDLE_ID
    release = CURRENT.parent / manifest["release_id"][:24]
    if not (package / "staged.json").exists():
        stage(package, manifest, release)
    else:
        staged = json.loads((package / "staged.json").read_text())
        assert staged["manifest_sha256"] == digest(package / "package.json")
        assert staged["release"] == str(release)
    if args.stage_only:
        return
    baseline = version()
    assert baseline["casandra_bundle_manifest_sha256"] == OLD_PIN
    if backup.exists():
        # A failed activation may have restored this exact baseline already.
        assert (backup / "base.env").read_bytes() == BASE.read_bytes()
        assert (backup / "selection.env").read_bytes() == SELECTION.read_bytes()
        assert (backup / "previous-release.txt").read_text().strip() == str(CURRENT.resolve())
    else:
        backup.mkdir(mode=0o700)
        shutil.copy2(BASE, backup / "base.env")
        shutil.copy2(SELECTION, backup / "selection.env")
        (backup / "previous-release.txt").write_text(str(CURRENT.resolve()) + "\n")
    save(package / "baseline.json", baseline)
    try:
        run("systemctl", "stop", API, CLEANUP, "casandra-web-cleanup.service")
        drain()
        retained = query("SELECT job_id,status,attempt,summary_json,token_digest FROM jobs")
        run("systemctl", "stop", WORKER)
        lines = BASE.read_text().splitlines()
        lines = [line for line in lines if not line.startswith("CASANDRA_WEB_CASANDRA_EXPECTED_VERSION=")]
        lines.append("CASANDRA_WEB_CASANDRA_EXPECTED_VERSION=casandra 0.3.0.dev2")
        atomic(BASE, ("\n".join(lines) + "\n").encode())
        atomic(SELECTION, (f"CASANDRA_WEB_MODEL_NAME={BUNDLE_ID}\n"
            f"CASANDRA_WEB_MODEL_REGISTRY={release}/registry.json\n").encode())
        select_release(release)
        run("systemctl", "reset-failed", WORKER, API)
        run("systemctl", "start", WORKER, API)
        current = wait_ready(PIN)
        assert current["casandra_program_version"] == "0.3.0.dev2"
        assert current["web_release_id"] == manifest["release_id"]
        assert retained == query("SELECT job_id,status,attempt,summary_json,token_digest FROM jobs")
        run("systemctl", "start", CLEANUP)
        run("bash", package / "verify-deployment.sh")
        save(package / "activated.json", {"status": "activated", "version": current,
            "retained_jobs_unchanged": len(retained), "rollback_release": str(CURRENT.parent / baseline["web_release_id"][:24])})
        print(json.dumps(current), flush=True)
    except BaseException:
        restore(backup)
        raise


if __name__ == "__main__":
    main()

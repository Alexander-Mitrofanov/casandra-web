from __future__ import annotations

import base64
import csv
import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

DIST_INFO = "casandra_web-0.1.0.dist-info"
ENTRY_POINTS = """[console_scripts]
casandra-web-api = casandra_web.api:main
casandra-web-cleanup = casandra_web.cleanup:main
casandra-web-worker = casandra_web.worker:main
"""
METADATA = """Metadata-Version: 2.1
Name: casandra-web
Version: 0.1.0
Requires-Python: >=3.10
Requires-Dist: fastapi==0.139.2
Requires-Dist: pydantic==2.13.4
Requires-Dist: uvicorn[standard]==0.51.0
"""


def _template_wheel(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("casandra_web/__init__.py", "OLD_PAYLOAD = True\n")
        archive.writestr("casandra_web/stale.py", "STALE_PAYLOAD = True\n")
        archive.writestr(f"{DIST_INFO}/METADATA", METADATA)
        archive.writestr(
            f"{DIST_INFO}/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr(f"{DIST_INFO}/entry_points.txt", ENTRY_POINTS)
        archive.writestr(f"{DIST_INFO}/top_level.txt", "casandra_web\n")
        archive.writestr(f"{DIST_INFO}/RECORD", "stale,sha256=stale,1\n")


def test_offline_wheel_rebuild_is_deterministic_and_uses_exact_source(tmp_path):
    root = Path(__file__).resolve().parents[2]
    script = root / "deploy/rebuild-backend-wheel.py"
    source = tmp_path / "source"
    package = source / "src/casandra_web"
    package.mkdir(parents=True)
    expected = {
        "casandra_web/__init__.py": b'__version__ = "0.1.0"\n',
        "casandra_web/api.py": b"def main():\n    return 0\n",
    }
    for relative, content in expected.items():
        destination = source / "src" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    (source / "pyproject.toml").write_text(
        """[project]
name = "casandra-web"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
  "fastapi==0.139.2",
  "pydantic==2.13.4",
  "uvicorn[standard]==0.51.0",
]
""",
        encoding="utf-8",
    )
    template = tmp_path / "casandra_web-0.1.0-py3-none-any.whl"
    _template_wheel(template)
    outputs = [tmp_path / f"derived-{index}.whl" for index in range(2)]
    for output in outputs:
        subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-S",
                str(script),
                "--template",
                str(template),
                "--source",
                str(source),
                "--output",
                str(output),
            ],
            check=True,
        )
    assert outputs[0].read_bytes() == outputs[1].read_bytes()

    with zipfile.ZipFile(outputs[0]) as archive:
        payload = {name: archive.read(name) for name in archive.namelist()}
    for name, content in expected.items():
        assert payload[name] == content
        assert b"OLD_PAYLOAD" not in payload[name]
    assert "casandra_web/stale.py" not in payload

    record_name = f"{DIST_INFO}/RECORD"
    rows = {
        row[0]: row[1:] for row in csv.reader(payload[record_name].decode("utf-8").splitlines())
    }
    assert set(rows) == set(payload)
    assert rows[record_name] == ["", ""]
    for name, content in payload.items():
        if name == record_name:
            continue
        encoded = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=")
        assert rows[name] == [f"sha256={encoded.decode('ascii')}", str(len(content))]

    (source / "pyproject.toml").write_text(
        (source / "pyproject.toml")
        .read_text(encoding="utf-8")
        .replace("fastapi==0.139.2", "fastapi==9.9.9"),
        encoding="utf-8",
    )
    rejected = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-S",
            str(script),
            "--template",
            str(template),
            "--source",
            str(source),
            "--output",
            str(tmp_path / "metadata-drift.whl"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "metadata differs" in rejected.stderr
    assert not (tmp_path / "metadata-drift.whl").exists()

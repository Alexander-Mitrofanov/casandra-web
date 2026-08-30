#!/usr/bin/env python3
"""Rebuild the reviewed backend wheel metadata around exact release sources."""

from __future__ import annotations

import argparse
import base64
import csv
import email.policy
import hashlib
import io
import os
import re
import stat
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

import tomllib

DIST_INFO = "casandra_web-0.1.0.dist-info"
RECORD = f"{DIST_INFO}/RECORD"
EXPECTED_METADATA = {
    f"{DIST_INFO}/METADATA",
    f"{DIST_INFO}/WHEEL",
    f"{DIST_INFO}/entry_points.txt",
    f"{DIST_INFO}/top_level.txt",
    RECORD,
}
EXPECTED_ENTRY_POINTS = b"""[console_scripts]
casandra-web-api = casandra_web.api:main
casandra-web-cleanup = casandra_web.cleanup:main
casandra-web-worker = casandra_web.worker:main
"""
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name


def _normalized_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _source_metadata(source: Path) -> tuple[str, str, str, set[str], set[str]]:
    pyproject_path = source / "pyproject.toml"
    if not pyproject_path.is_file() or pyproject_path.is_symlink():
        raise ValueError("release pyproject.toml is unavailable")
    project = tomllib.loads(pyproject_path.read_text(encoding="utf-8")).get("project")
    if not isinstance(project, dict):
        raise TypeError("release project metadata is unavailable")
    name = project.get("name")
    version = project.get("version")
    requires_python = project.get("requires-python")
    dependencies = project.get("dependencies")
    optional = project.get("optional-dependencies", {})
    if (
        not isinstance(name, str)
        or not isinstance(version, str)
        or not isinstance(requires_python, str)
        or not isinstance(dependencies, list)
        or not all(isinstance(value, str) and value.strip() == value for value in dependencies)
        or not isinstance(optional, dict)
    ):
        raise ValueError("release project metadata is malformed")
    expected_requirements = set(dependencies)
    expected_extras: set[str] = set()
    for extra, requirements in optional.items():
        if (
            not isinstance(extra, str)
            or not extra
            or not isinstance(requirements, list)
            or not all(
                isinstance(value, str) and value.strip() == value and ";" not in value
                for value in requirements
            )
        ):
            raise ValueError("release optional dependencies are malformed")
        expected_extras.add(extra)
        expected_requirements.update(
            f'{requirement}; extra == "{extra}"' for requirement in requirements
        )
    if len(expected_requirements) != len(dependencies) + sum(map(len, optional.values())):
        raise ValueError("release dependencies contain duplicates")
    return name, version, requires_python, expected_requirements, expected_extras


def _template_metadata(path: Path, source: Path) -> dict[str, bytes]:
    if path.name != "casandra_web-0.1.0-py3-none-any.whl":
        raise ValueError("template wheel filename is not reviewed")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)) or not all(_safe_member(name) for name in names):
            raise ValueError("template wheel has duplicate or unsafe members")
        for item in infos:
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError("template wheel contains a symbolic link")
        metadata_names = {name for name in names if name.startswith(f"{DIST_INFO}/")}
        if metadata_names != EXPECTED_METADATA:
            raise ValueError("template wheel metadata layout is not reviewed")
        if any(not name.startswith(("casandra_web/", f"{DIST_INFO}/")) for name in names):
            raise ValueError("template wheel contains an unexpected payload")
        metadata = {name: archive.read(name) for name in sorted(EXPECTED_METADATA - {RECORD})}
    source_name, source_version, source_python, source_requirements, source_extras = (
        _source_metadata(source)
    )
    package_metadata = BytesParser(policy=email.policy.default).parsebytes(
        metadata[f"{DIST_INFO}/METADATA"]
    )
    wheel_requirements = package_metadata.get_all("Requires-Dist", [])
    wheel_extras = package_metadata.get_all("Provides-Extra", [])
    if (
        _normalized_name(str(package_metadata.get("Name", ""))) != _normalized_name(source_name)
        or str(package_metadata.get("Version", "")) != source_version
        or str(package_metadata.get("Requires-Python", "")) != source_python
        or len(wheel_requirements) != len(set(wheel_requirements))
        or set(wheel_requirements) != source_requirements
        or len(wheel_extras) != len(set(wheel_extras))
        or set(wheel_extras) != source_extras
    ):
        raise ValueError("template wheel metadata differs from release pyproject.toml")
    if metadata[f"{DIST_INFO}/entry_points.txt"] != EXPECTED_ENTRY_POINTS:
        raise ValueError("template wheel entry points are not reviewed")
    if b"Tag: py3-none-any" not in metadata[f"{DIST_INFO}/WHEEL"].splitlines():
        raise ValueError("template wheel compatibility tag is not reviewed")
    return metadata


def _source_payload(source: Path) -> dict[str, bytes]:
    package = source / "src" / "casandra_web"
    if not package.is_dir() or package.is_symlink():
        raise ValueError("release source package is unavailable")
    payload: dict[str, bytes] = {}
    for path in sorted(package.rglob("*")):
        if path.is_symlink():
            raise ValueError("release source package contains a symbolic link")
        if path.is_dir():
            continue
        if not path.is_file() or path.suffix != ".py":
            raise ValueError("release source package contains a non-Python payload")
        relative = path.relative_to(source / "src").as_posix()
        if not _safe_member(relative):
            raise ValueError("release source package contains an unsafe path")
        payload[relative] = path.read_bytes()
    if "casandra_web/__init__.py" not in payload:
        raise ValueError("release source package is incomplete")
    return payload


def _record(payload: dict[str, bytes]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    for name in sorted(payload):
        digest = base64.urlsafe_b64encode(hashlib.sha256(payload[name]).digest()).rstrip(b"=")
        writer.writerow((name, f"sha256={digest.decode('ascii')}", len(payload[name])))
    writer.writerow((RECORD, "", ""))
    return output.getvalue().encode("utf-8")


def _write_wheel(output: Path, payload: dict[str, bytes]) -> None:
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    if output.exists() or output.is_symlink() or temporary.exists() or temporary.is_symlink():
        raise ValueError("output wheel path already exists")
    try:
        with zipfile.ZipFile(
            temporary, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for name in sorted(payload):
                info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, payload[name], compresslevel=9)
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.template.is_symlink() or not arguments.template.is_file():
        raise SystemExit("template wheel must be a regular file")
    payload = _source_payload(arguments.source)
    payload.update(_template_metadata(arguments.template, arguments.source))
    payload[RECORD] = _record(payload)
    _write_wheel(arguments.output, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

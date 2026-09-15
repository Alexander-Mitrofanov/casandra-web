"""Operator-owned model bundles; no model paths are accepted from API clients.

Register a trusted bundle with ``python -m casandra_web.model_registry``.
Registration verifies files without deserializing the scientific estimator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def validate_name(name: str) -> None:
    if _NAME.fullmatch(name) is None:
        raise ValueError("invalid operator model name")


def verify_bundle(directory: Path, expected_sha256: str) -> tuple[str, str]:
    """Check the pinned manifest and every listed artifact before model loading."""
    manifest_path = directory / "manifest.json"
    if not directory.is_absolute() or not directory.is_dir():
        raise ValueError("model bundle must be an existing absolute directory")
    if _SHA256.fullmatch(expected_sha256) is None:
        raise ValueError("model manifest pin must be lowercase SHA-256")
    if sha256(manifest_path) != expected_sha256:
        raise ValueError("model bundle manifest does not match its registry pin")
    manifest = json.loads(manifest_path.read_text())
    artifacts = manifest.get("artifacts")
    required = {"config.json", "protein/manifest.json", "cassette_architecture/manifest.json"}
    if not isinstance(artifacts, dict) or not required.issubset(artifacts):
        raise ValueError("model bundle manifest lacks required artifacts")
    for relative, record in artifacts.items():
        path = directory / relative
        if (
            Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not path.resolve().is_relative_to(directory.resolve())
            or not path.is_file()
        ):
            raise ValueError("model bundle artifact is missing or escapes the bundle")
        if path.stat().st_size != record.get("size") or sha256(path) != record.get("sha256"):
            raise ValueError(f"model bundle artifact integrity failed: {relative}")
    config = json.loads((directory / "config.json").read_text())
    bundle_id, role = config.get("bundle_id"), config.get("bundle_role")
    if (
        not isinstance(bundle_id, str)
        or _NAME.fullmatch(bundle_id) is None
        or not isinstance(role, str)
        or _NAME.fullmatch(role) is None
        or manifest.get("bundle_id") != bundle_id
    ):
        raise ValueError("model bundle identity is invalid or inconsistent")
    return bundle_id, role


@dataclass(frozen=True)
class RegisteredModel:
    directory: Path
    bundle_id: str
    manifest_sha256: str
    program_version: str
    result_schema_version: int
    bundle_role: str

    @property
    def identity(self) -> tuple[str, str, str, int, str]:
        return (
            self.bundle_id, self.manifest_sha256, self.program_version,
            self.result_schema_version, self.bundle_role,
        )


def load_model(registry_path: Path, name: str, *, data_root: Path) -> RegisteredModel:
    validate_name(name)
    if not registry_path.is_absolute():
        raise ValueError("model registry path must be absolute")
    registry = json.loads(registry_path.read_text())
    if registry.get("schema_version") != 1 or not isinstance(registry.get("models"), dict):
        raise ValueError("invalid model registry schema")
    if name not in registry["models"]:
        raise ValueError(f"operator model is not registered: {name}")
    entry = registry["models"][name]
    if not isinstance(entry, dict):
        raise TypeError("registered model entry must be an object")
    directory = Path(entry["directory"])
    if directory.resolve().is_relative_to(data_root.resolve()):
        raise ValueError("model bundles must be outside the writable job data directory")
    bundle_id, role = verify_bundle(directory, entry["manifest_sha256"])
    if bundle_id != entry.get("bundle_id") or role != entry.get("bundle_role"):
        raise ValueError("model bundle identity does not match its registry entry")
    version, schema = entry.get("program_version"), entry.get("result_schema_version")
    if not isinstance(version, str) or _NAME.fullmatch(version) is None:
        raise ValueError("invalid registered program version")
    if type(schema) is not int or not 1 <= schema <= 1_000:
        raise ValueError("invalid registered result schema version")
    return RegisteredModel(directory.resolve(), bundle_id, entry["manifest_sha256"],
                           version, schema, role)


def register(registry_path: Path, name: str, directory: Path,
             program_version: str, result_schema_version: int) -> dict:
    validate_name(name)
    if name == "default":
        raise ValueError("default is reserved for the packaged model")
    directory = directory.resolve(strict=True)
    pin = sha256(directory / "manifest.json")
    bundle_id, role = verify_bundle(directory, pin)
    if _NAME.fullmatch(program_version) is None or not 1 <= result_schema_version <= 1_000:
        raise ValueError("invalid runtime version or result schema")
    entry = {"directory": str(directory), "bundle_id": bundle_id, "manifest_sha256": pin,
             "program_version": program_version, "result_schema_version": result_schema_version,
             "bundle_role": role}
    registry = (json.loads(registry_path.read_text()) if registry_path.exists()
                else {"schema_version": 1, "models": {}})
    if registry.get("schema_version") != 1 or not isinstance(registry.get("models"), dict):
        raise ValueError("invalid model registry schema")
    existing = registry["models"].get(name)
    if existing is not None and existing != entry:
        raise ValueError("model name already identifies a different bundle; use a new name")
    registry["models"][name] = entry
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".model-registry-", dir=registry_path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(registry, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o644)
        os.replace(temporary, registry_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--program-version", required=True)
    parser.add_argument("--result-schema-version", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(register(args.registry.resolve(), args.name, args.bundle,
                              args.program_version, args.result_schema_version), indent=2))


if __name__ == "__main__":
    main()

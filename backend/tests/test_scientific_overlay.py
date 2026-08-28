import hashlib
import importlib.util
import json
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
OVERLAY_ROOT = WEB_ROOT / "deploy/docker/casandra-tool-overlay/src/casandra"
RELEASE_LOCK = WEB_ROOT / "deploy/docker/casandra-tool-release.sha256"


class FixedArchitectureModel:
    def classify(self, *_args):
        return "II-A", 0.54


def _overlay_hybrid_module():
    path = OVERLAY_ROOT / "cassette_hybrid.py"
    spec = importlib.util.spec_from_file_location("casandra_web_test_overlay_hybrid", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tracked_scientific_overlay_routes_type_ii_and_preserves_direct_evidence():
    module = _overlay_hybrid_module()
    direct = {
        "class": "2",
        "type": "II",
        "subtype": "II-C",
        "confidence": {"subtype_vote_fraction": 1.0},
    }

    result = module.classify_hybrid_cassette(
        {"classification": direct}, FixedArchitectureModel(), {}, {}
    )

    assert result["subtype"] == "II-A"
    assert result["method"] == "type_ii_ordered_profile_architecture_extratrees"
    assert result["direct_profile_result"] is direct


def test_tracked_bundle_metadata_and_release_lock_match_the_overlay():
    config_path = OVERLAY_ROOT / "models/config.json"
    manifest_path = OVERLAY_ROOT / "models/manifest.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert config["bundle_id"] == manifest["bundle_id"]
    assert config["routing_policy_evidence"]["aggregate_accuracy_reestimated"] is False
    assert manifest["type_ii_routing_validation"]["aggregate_accuracy_reestimated"] is False

    config_record = manifest["artifacts"]["config.json"]
    assert config_path.stat().st_size == config_record["size"]
    assert hashlib.sha256(config_path.read_bytes()).hexdigest() == config_record["sha256"]

    locked = {
        relative: digest
        for digest, relative in (
            line.split(maxsplit=1)
            for line in RELEASE_LOCK.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    for relative, path in {
        "src/casandra/cassette_hybrid.py": OVERLAY_ROOT / "cassette_hybrid.py",
        "src/casandra/models/config.json": config_path,
        "src/casandra/models/manifest.json": manifest_path,
    }.items():
        assert locked[relative] == hashlib.sha256(path.read_bytes()).hexdigest()

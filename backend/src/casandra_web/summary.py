"""Build a bounded visualization projection without raw biological sequences."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

_MAX_JSON_BYTES = 25_000_000
_MAX_CAS_PROTEINS = 5_000
_MAX_CASSETTES = 1_000
_MAX_ARRAYS = 2_000
_MAX_ARRAYS_TOTAL = 100_000
_CRISPR_CATEGORIES = ("Bona-fide", "Possible", "Low score")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SummaryError(RuntimeError):
    pass


def _read_json(path: Path) -> object:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > _MAX_JSON_BYTES:
        raise SummaryError(f"required bounded JSON is unavailable: {path.name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SummaryError(f"invalid JSON: {path.name}") from error


def _jsonl(path: Path, maximum: int = 2_000_000) -> Iterable[Mapping[str, Any]]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 250_000_000:
        raise SummaryError(f"required bounded JSONL is unavailable: {path.name}")
    try:
        with path.open(encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index >= maximum:
                    raise SummaryError(f"{path.name} contains too many rows")
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, Mapping):
                    raise SummaryError(f"{path.name} contains a non-object row")
                yield value
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SummaryError(f"invalid JSONL: {path.name}") from error


def _fasta_sources(path: Path) -> dict[str, dict[str, int | str]]:
    sources: dict[str, dict[str, int | str]] = {}
    current: str | None = None
    sequence_parts: list[str] = []

    def finish() -> None:
        if current is None:
            return
        sequence = "".join(sequence_parts).upper()
        sources[current] = {
            "length": len(sequence),
            "sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
        }

    try:
        for raw in path.read_text(encoding="ascii").splitlines():
            if raw.startswith(">"):
                finish()
                current = raw[1:].split()[0]
                if current in sources:
                    raise SummaryError("normalized FASTA contains duplicate IDs")
                sequence_parts = []
            elif raw.strip():
                if current is None:
                    raise SummaryError("normalized FASTA has sequence before a header")
                sequence_parts.append(raw.strip())
        finish()
    except (OSError, UnicodeError) as error:
        raise SummaryError("normalized FASTA could not be read") from error
    return sources


def _finite(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return value
    if isinstance(value, str):
        try:
            converted = float(value)
        except ValueError:
            return None
        return converted if math.isfinite(converted) else None
    return None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _validate_casandra_output(
    input_path: Path,
    casandra_root: Path,
    run: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> None:
    schema_version = run.get("schema_version")
    if schema_version not in {4, 5} or manifest.get("schema_version") != schema_version:
        raise SummaryError("unsupported CasAndra output schema")
    input_digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
    if schema_version == 4:
        run_input_digest = _mapping(run.get("input")).get("sha256")
    else:
        inputs = run.get("inputs")
        run_input_digest = None
        if isinstance(inputs, list) and len(inputs) == 1:
            record = _mapping(inputs[0])
            if record.get("kind") == "genome_fasta":
                run_input_digest = record.get("sha256")
    if run_input_digest != input_digest:
        raise SummaryError("CasAndra input provenance does not match the submitted FASTA")
    bundle_digest = manifest.get("bundle_manifest_sha256")
    if not isinstance(bundle_digest, str) or _SHA256.fullmatch(bundle_digest) is None:
        raise SummaryError("CasAndra model-bundle provenance is unavailable")
    files = _mapping(manifest.get("files"))
    required = {"proteins.jsonl", "cassettes.jsonl", "run.json"}
    if not required.issubset(files) or len(files) > 1_000:
        raise SummaryError("CasAndra output manifest is incomplete")
    root = casandra_root.resolve()
    for relative_name, raw_record in files.items():
        if not isinstance(relative_name, str):
            raise SummaryError("CasAndra output manifest contains an invalid path")
        relative = Path(relative_name)
        if relative.is_absolute() or ".." in relative.parts:
            raise SummaryError("CasAndra output manifest contains an unsafe path")
        record = _mapping(raw_record)
        expected_size = record.get("size")
        expected_digest = record.get("sha256")
        path = casandra_root / relative
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as error:
            raise SummaryError("CasAndra output manifest references an unavailable file") from error
        if (
            not resolved.is_file()
            or resolved.is_symlink()
            or not isinstance(expected_size, int)
            or resolved.stat().st_size != expected_size
            or not isinstance(expected_digest, str)
            or _SHA256.fullmatch(expected_digest) is None
            or hashlib.sha256(resolved.read_bytes()).hexdigest() != expected_digest
        ):
            raise SummaryError("CasAndra output does not match its manifest")


def _feature_interval(
    row: Mapping[str, Any], contig_lengths: Mapping[str, int], label: str
) -> tuple[str, int, int]:
    contig_id = str(row.get("contig_id") or "")
    start = row.get("start_1based")
    end = row.get("end_1based_inclusive")
    if (
        contig_id not in contig_lengths
        or isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start < 1
        or end < start
        or end > contig_lengths.get(contig_id, 0)
    ):
        raise SummaryError(f"CasAndra reported an invalid {label} source interval")
    return contig_id, start, end


def _first(mapping: Mapping[str, Any], names: tuple[str, ...]) -> object | None:
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _report_arrays(document: object) -> list[Mapping[str, Any]]:
    root = _mapping(document)
    arrays = root.get("arrays")
    if not isinstance(arrays, list) or any(not isinstance(item, Mapping) for item in arrays):
        raise SummaryError("CRISPRidentify report arrays must be a list of objects")
    return arrays


def _source_id(document: object, fallback: str) -> str:
    root = _mapping(document)
    source = _mapping(root.get("source"))
    return str(source.get("id") or root.get("source_id") or fallback)[:200]


def _array_view(array: Mapping[str, Any], source_id: str) -> dict[str, Any]:
    orientation = _mapping(_first(array, ("orientation", "direction", "strand")))
    raw_orientation = _first(array, ("orientation", "direction", "strand"))
    strand = (
        _first(orientation, ("strand", "label", "direction", "status"))
        if orientation
        else raw_orientation
    )
    spacers = _first(array, ("spacers", "spacer_sequences"))
    spacer_count = array.get("spacer_count")
    if not isinstance(spacer_count, int) and isinstance(spacers, list):
        spacer_count = len(spacers)
    interval = _mapping(array.get("source_interval"))
    return {
        "array_id": str(_first(array, ("id", "array_id", "name")) or "unknown")[:240],
        "contig_id": source_id,
        "start": interval.get("start"),
        "end": interval.get("end"),
        "strand": None if strand is None else str(strand)[:40],
        "category": str(
            _first(array, ("category", "classification", "category_name")) or "Unknown"
        )[:80],
        "repeat_count": array.get("repeat_count")
        if isinstance(array.get("repeat_count"), int)
        else None,
        "spacer_count": spacer_count if isinstance(spacer_count, int) else None,
        "model_score": _finite(_first(array, ("model_score", "certainty_score", "score"))),
        "model_score_is_probability": False,
    }


def _validated_report_source(
    document: object,
    expected_sources: Mapping[str, Mapping[str, int | str]],
    path: Path,
) -> str:
    root = _mapping(document)
    schema = _mapping(root.get("schema"))
    version = str(schema.get("version") or "")
    if schema.get("name") != "CRISPRidentify-report" or version != "1.1.0":
        raise SummaryError(f"unsupported CRISPRidentify report schema: {path.name}")
    coordinates = _mapping(root.get("coordinate_system"))
    if (
        coordinates.get("indexing") != 1
        or coordinates.get("end_inclusive") is not True
        or coordinates.get("reference") != "input_forward_strand"
        or coordinates.get("orientation_is_separate") is not True
    ):
        raise SummaryError("CRISPRidentify reported an unsupported coordinate system")
    source = _mapping(root.get("source"))
    source_id = str(source.get("id") or "")
    expected = expected_sources.get(source_id)
    if expected is None:
        raise SummaryError("CRISPRidentify report source does not match the submitted FASTA")
    if (
        source.get("length") != expected["length"]
        or source.get("sha256_scope") != "uppercase_sequence"
        or source.get("sha256") != expected["sha256"]
    ):
        raise SummaryError("CRISPRidentify source provenance does not match the submitted FASTA")
    return source_id


def _arrays(
    identify_root: Path, expected_sources: Mapping[str, Mapping[str, int | str]]
) -> list[dict[str, Any]]:
    arrays: list[dict[str, Any]] = []
    report_paths = sorted((identify_root / "crispridentify").rglob("report.json"))
    if len(report_paths) != len(expected_sources):
        raise SummaryError("CRISPRidentify did not produce exactly one report per FASTA source")
    seen_sources: set[str] = set()
    seen_array_ids: set[tuple[str, str]] = set()
    for path in report_paths:
        document = _read_json(path)
        source_id = _validated_report_source(document, expected_sources, path)
        if source_id in seen_sources:
            raise SummaryError("CRISPRidentify produced duplicate reports for a FASTA source")
        seen_sources.add(source_id)

        root = _mapping(document)
        raw_arrays = _report_arrays(document)
        category_counts = {name: 0 for name in _CRISPR_CATEGORIES}
        accepted_count = 0
        validation = _mapping(root.get("validation"))
        if (
            validation.get("status") != "valid"
            or validation.get("method") != "independent_original_sequence_slicing"
            or validation.get("validated_array_count") != len(raw_arrays)
            or validation.get("invalid_array_count") != 0
        ):
            raise SummaryError("CRISPRidentify report source validation is unavailable")

        for raw in raw_arrays:
            array_id = raw.get("id")
            category = raw.get("category")
            array_validation = _mapping(raw.get("validation"))
            if not isinstance(array_id, str) or not array_id.strip():
                raise SummaryError("CRISPRidentify reported an empty array identifier")
            array_key = (source_id, array_id)
            if array_key in seen_array_ids:
                raise SummaryError("CRISPRidentify reported a duplicate array identifier")
            seen_array_ids.add(array_key)
            if category not in category_counts:
                raise SummaryError("CRISPRidentify reported an unsupported array category")
            category_counts[str(category)] += 1
            if category in {"Bona-fide", "Possible"}:
                accepted_count += 1
            if (
                array_validation.get("status") != "valid"
                or array_validation.get("source_reconstructed") is not True
                or array_validation.get("method")
                != "independent_original_sequence_slicing"
            ):
                raise SummaryError("CRISPRidentify array source validation is unavailable")

            view = _array_view(raw, source_id)
            start = view["start"]
            end = view["end"]
            strand = view["strand"]
            repeat_count = view["repeat_count"]
            spacer_count = view["spacer_count"]
            score_source = _first(raw, ("model_score", "certainty_score", "score"))
            if (
                isinstance(start, bool)
                or isinstance(end, bool)
                or not isinstance(start, int)
                or not isinstance(end, int)
                or start < 1
                or end < start
                or end > int(expected_sources[source_id]["length"])
            ):
                raise SummaryError("CRISPRidentify reported an invalid source interval")
            interval = _mapping(raw.get("source_interval"))
            if interval.get("length") != end - start + 1:
                raise SummaryError("CRISPRidentify reported inconsistent interval geometry")
            if strand not in {None, "+", "-"}:
                raise SummaryError("CRISPRidentify reported an invalid array strand")
            if (
                isinstance(repeat_count, bool)
                or not isinstance(repeat_count, int)
                or repeat_count < 1
                or isinstance(spacer_count, bool)
                or not isinstance(spacer_count, int)
                or spacer_count < 0
            ):
                raise SummaryError("CRISPRidentify reported invalid repeat or spacer counts")
            if score_source is not None and _finite(score_source) is None:
                raise SummaryError("CRISPRidentify reported a non-finite model score")
            if category in {"Bona-fide", "Possible"}:
                arrays.append(view)
                if len(arrays) > _MAX_ARRAYS_TOTAL:
                    raise SummaryError("CRISPRidentify reported too many accepted arrays")

        summary = _mapping(root.get("summary"))
        if (
            summary.get("array_count") != len(raw_arrays)
            or summary.get("accepted_array_count") != accepted_count
            or summary.get("category_counts") != category_counts
        ):
            raise SummaryError("CRISPRidentify report summary disagrees with its arrays")
    if seen_sources != set(expected_sources):
        raise SummaryError("CRISPRidentify did not produce exactly one report per FASTA source")
    arrays.sort(
        key=lambda item: (
            str(item["contig_id"]),
            int(item["start"]),
            int(item["end"]),
            str(item["array_id"]),
        )
    )
    return arrays


def _nearest_array(
    cassette: Mapping[str, Any], arrays: Iterable[Mapping[str, Any]]
) -> dict[str, Any] | None:
    same = [array for array in arrays if array["contig_id"] == cassette["contig_id"]]
    if not same:
        return None
    start = int(cassette["start"])
    end = int(cassette["end"])

    def distance(array: Mapping[str, Any]) -> int:
        array_start = int(array["start"])
        array_end = int(array["end"])
        if array_end < start:
            return start - array_end - 1
        if array_start > end:
            return array_start - end - 1
        return 0

    nearest = min(
        same, key=lambda item: (distance(item), int(item["start"]), str(item["array_id"]))
    )
    return {
        "array_id": nearest["array_id"],
        "distance_bp": distance(nearest),
        "interpretation": "coordinate_co_location_only",
    }


def build_summary(
    job_root: Path, result_root: Path, *, requested_gene_mode: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    input_path = job_root / "input" / "genome.fasta"
    casandra_root = result_root / "casandra"
    identify_root = result_root / "identify"
    fasta_sources = _fasta_sources(input_path)
    contig_lengths = {name: int(value["length"]) for name, value in fasta_sources.items()}
    run = _mapping(_read_json(casandra_root / "run.json"))
    manifest = _mapping(_read_json(casandra_root / "manifest.json"))
    _validate_casandra_output(input_path, casandra_root, run, manifest)

    cas_proteins: list[dict[str, Any]] = []
    all_genes: dict[str, Mapping[str, Any]] = {}
    selected_gene_modes: set[str] = set()
    translation_table_counts: dict[str, int] = {}
    caller_versions: set[str] = set()
    for row in _jsonl(casandra_root / "proteins.jsonl"):
        protein_id = str(row.get("protein_id") or "")
        if not protein_id:
            raise SummaryError("CasAndra protein output contains an empty identifier")
        if protein_id in all_genes:
            raise SummaryError("CasAndra protein output contains duplicate identifiers")
        all_genes[protein_id] = row
        caller = _mapping(row.get("caller"))
        selected_mode = caller.get("mode")
        requested_mode = caller.get("requested_mode")
        translation_table = row.get("translation_table")
        partial_5prime = row.get("partial_5prime")
        partial_3prime = row.get("partial_3prime")
        if (
            caller.get("program") != "Pyrodigal"
            or selected_mode not in {"single", "meta"}
            or requested_mode != requested_gene_mode
            or row.get("translation_policy") != "caller_selected_per_gene"
            or isinstance(translation_table, bool)
            or not isinstance(translation_table, int)
            or not 1 <= translation_table <= 33
            or not isinstance(partial_5prime, bool)
            or not isinstance(partial_3prime, bool)
        ):
            raise SummaryError("CasAndra gene-calling provenance is invalid")
        selected_gene_modes.add(str(selected_mode))
        table_key = str(translation_table)
        translation_table_counts[table_key] = translation_table_counts.get(table_key, 0) + 1
        caller_version = caller.get("version")
        if isinstance(caller_version, str) and caller_version:
            caller_versions.add(caller_version[:80])
        prediction = _mapping(row.get("prediction"))
        if not prediction.get("is_cas"):
            continue
        contig_id, start, end = _feature_interval(row, contig_lengths, "protein")
        classification = _mapping(prediction.get("classification"))
        cas_proteins.append(
            {
                "protein_id": protein_id[:240],
                "contig_id": contig_id[:200],
                "start": start,
                "end": end,
                "strand": str(row.get("strand") or ".")[:8],
                "type": classification.get("type"),
                "subtype": classification.get("subtype"),
                "profile": prediction.get("best_positive_profile"),
                "score_margin": _finite(prediction.get("score_margin")),
                "profile_score": _finite(prediction.get("positive_profile_score")),
                "translation_table": translation_table,
                "partial_5prime": partial_5prime,
                "partial_3prime": partial_3prime,
                "score_is_probability": False,
                "cassette_id": None,
            }
        )

    cassette_rows = list(_jsonl(casandra_root / "cassettes.jsonl"))
    cassette_views: list[dict[str, Any]] = []
    protein_to_cassette: dict[str, str] = {}
    cassette_ids: set[str] = set()
    for row in cassette_rows:
        final = _mapping(row.get("final_classification"))
        gate = _mapping(row.get("genome_evidence_gate"))
        if not isinstance(gate.get("accepted"), bool) or not isinstance(
            gate.get("rule"), str
        ) or not str(gate.get("rule")).strip():
            raise SummaryError("CasAndra cassette evidence-gate provenance is invalid")
        cassette_id = str(row.get("cassette_id") or "")[:300]
        if not cassette_id or cassette_id in cassette_ids:
            raise SummaryError("CasAndra cassette output contains an invalid identifier")
        cassette_ids.add(cassette_id)
        contig_id, start, end = _feature_interval(row, contig_lengths, "cassette")
        cas_protein_ids = [
            str(item)[:240] for item in row.get("cas_protein_ids", []) if isinstance(item, str)
        ]
        if any(
            protein_id not in all_genes
            or not _mapping(all_genes[protein_id].get("prediction")).get("is_cas")
            for protein_id in cas_protein_ids
        ):
            raise SummaryError("CasAndra cassette references an unavailable Cas protein")
        view = {
            "cassette_id": cassette_id,
            "contig_id": contig_id[:200],
            "start": start,
            "end": end,
            "cas_gene_count": int(row.get("cas_gene_count") or 0),
            "class": final.get("class"),
            "type": final.get("type"),
            "subtype": final.get("subtype"),
            "method": final.get("method"),
            "confidence": _finite(final.get("confidence")),
            "confidence_is_probability": False,
            "evidence_gate": {
                "accepted": gate["accepted"],
                "rule": gate.get("rule"),
            },
            "cas_protein_ids": cas_protein_ids,
        }
        cassette_views.append(view)
        for protein_id in view["cas_protein_ids"]:
            protein_to_cassette[protein_id] = cassette_id
    for protein in cas_proteins:
        protein["cassette_id"] = protein_to_cassette.get(str(protein["protein_id"]))

    arrays = _arrays(identify_root, fasta_sources)
    warnings: list[str] = []
    for cassette in cassette_views:
        cassette["nearest_array"] = _nearest_array(cassette, arrays)

    projected_arrays = arrays[:_MAX_ARRAYS]
    if len(arrays) > len(projected_arrays):
        warnings.append("CRISPR array details were truncated in the interactive projection.")

    total_proteins = len(cas_proteins)
    total_cassettes = len(cassette_views)
    if (
        run.get("genes") != len(all_genes)
        or run.get("cas_proteins") != total_proteins
        or run.get("cas_cassettes") != total_cassettes
    ):
        raise SummaryError("CasAndra run counts do not match its result records")
    if total_proteins > _MAX_CAS_PROTEINS:
        cas_proteins = cas_proteins[:_MAX_CAS_PROTEINS]
        warnings.append("Cas protein details were truncated in the interactive projection.")
    if total_cassettes > _MAX_CASSETTES:
        cassette_views = cassette_views[:_MAX_CASSETTES]
        warnings.append("Cassette details were truncated in the interactive projection.")
    if not total_proteins:
        warnings.append("CasAndra found no Cas proteins in this input.")
    if not arrays:
        warnings.append("CRISPRidentify v2 found no accepted CRISPR arrays in this input.")
    warnings.extend(
        [
            "CasAndra calls are authoritative; CRISPR-array co-location never changes a Cas call or subtype.",
            "CasAndra margins, profile scores, and cassette confidence values are evidence scores, not calibrated probabilities.",
            "CRISPRidentify model scores are not calibrated probabilities; category is the primary interpretation.",
            "Coordinates are 1-based, end-inclusive, and shown in source-forward order; strand is reported separately.",
        ]
    )
    summary = {
        "schema_version": "1.0.0",
        "overview": {
            "contig_count": len(contig_lengths),
            "total_bases": sum(contig_lengths.values()),
            "gene_count": int(run.get("genes") or len(all_genes)),
            "cas_protein_count": int(run.get("cas_proteins") or total_proteins),
            "cassette_count": int(run.get("cas_cassettes") or total_cassettes),
            "crispr_array_count": len(arrays),
            "wall_seconds": _finite(run.get("wall_seconds")),
        },
        "contigs": [{"id": name, "length": length} for name, length in contig_lengths.items()],
        "cassettes": cassette_views,
        "cas_proteins": cas_proteins,
        "crispr_arrays": projected_arrays,
        "detail_truncated": {
            "cas_proteins": total_proteins > len(cas_proteins),
            "cassettes": total_cassettes > len(cassette_views),
            "crispr_arrays": len(arrays) > len(projected_arrays),
        },
        "warnings": warnings,
        "provenance": {
            "casandra_bundle_id": run.get("bundle_id"),
            "casandra_bundle_role": run.get("bundle_role"),
            "casandra_manifest_sha256": manifest.get("bundle_manifest_sha256"),
            "casandra_schema_version": run.get("schema_version"),
            "crispridentify_version": "2.0.0",
            "crispridentify_version_attestation": "image_VERSION_and_canonical_report_schema",
            "array_overlay_role": "independent_coordinate_overlay",
            "gene_calling": {
                "caller": "Pyrodigal",
                "caller_versions": sorted(caller_versions),
                "requested_mode": requested_gene_mode,
                "selected_modes": sorted(selected_gene_modes),
                "requested_translation_table": 11,
                "requested_translation_table_scope": "single_mode_training",
                "translation_policy": "caller_selected_per_gene",
                "translation_table_counts": translation_table_counts,
            },
        },
    }
    return summary, arrays

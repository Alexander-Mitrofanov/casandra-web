"""Build authenticated, complete result exports and interactive feature details."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote


class ExportError(RuntimeError):
    pass


_DNA = re.compile(r"^[ACGTRYSWKMBDHVN]*$")
_PROTEIN = re.compile(r"^[ABCDEFGHIKLMNPQRSTVWXYZJUO*\-]*$")
_COMPLEMENT = str.maketrans("ACGTRYSWKMBDHVN", "TGCAYRSWMKVHDBN")
_UNAMBIGUOUS_DNA = frozenset("ACGT")
_MAX_RESULT_ROWS = 2_000_000
_MAX_REPORTS = 10_000
_MAX_SPACERS_PER_ARRAY = 10_000
_CSV_FIELDS = (
    "feature_kind",
    "feature_ref",
    "feature_id",
    "input_index",
    "sequence_id",
    "contig_id",
    "start",
    "end",
    "strand",
    "result",
    "is_cas",
    "cas_family",
    "class",
    "type",
    "subtype",
    "profile",
    "residue_count",
    "repeat_count",
    "spacer_count",
    "cassette_id",
    "profile_score",
    "score_margin",
    "model_score",
    "method",
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _write_private_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
    os.chmod(path, 0o600)


def _read_fasta(path: Path, *, molecule: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    current_id: str | None = None
    parts: list[str] = []

    def finish() -> None:
        if current_id is None:
            return
        sequence = "".join(parts).upper()
        pattern = _PROTEIN if molecule == "protein" else _DNA
        if not sequence or pattern.fullmatch(sequence) is None:
            raise ExportError(f"normalized {molecule} FASTA contains an invalid sequence")
        records.append(
            {
                "id": current_id,
                "sequence": sequence,
                "length": len(sequence.rstrip("*")) if molecule == "protein" else len(sequence),
                "sha256": _sha256_text(sequence),
            }
        )

    try:
        for raw in path.read_text(encoding="ascii").splitlines():
            if raw.startswith(">"):
                finish()
                current_id = raw[1:].split()[0]
                if not current_id or current_id in seen:
                    raise ExportError("normalized FASTA contains an invalid identifier")
                seen.add(current_id)
                parts = []
            elif raw.strip():
                if current_id is None:
                    raise ExportError("normalized FASTA has sequence before a header")
                parts.append(raw.strip())
        finish()
    except (OSError, UnicodeError) as error:
        raise ExportError("normalized FASTA could not be read for export") from error
    if not records:
        raise ExportError("normalized FASTA contains no exportable records")
    return records


def _read_jsonl(path: Path, *, maximum: int = 100_000) -> list[Mapping[str, Any]]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 250_000_000:
        raise ExportError(f"validated result rows are unavailable: {path.name}")
    rows: list[Mapping[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                if len(rows) >= maximum:
                    raise ExportError(f"too many rows for interactive export: {path.name}")
                value = json.loads(line)
                if not isinstance(value, Mapping):
                    raise ExportError(f"invalid result row in {path.name}")
                rows.append(value)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ExportError(f"validated result rows could not be read: {path.name}") from error
    return rows


def _read_json(path: Path) -> Mapping[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 25_000_000:
        raise ExportError(f"validated result document is unavailable: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ExportError(f"validated result document could not be read: {path.name}") from error
    if not isinstance(value, Mapping):
        raise ExportError(f"validated result document is not an object: {path.name}")
    return value


def _reverse_complement(sequence: str) -> str:
    if _DNA.fullmatch(sequence) is None:
        raise ExportError("cannot orient a non-IUPAC DNA sequence")
    return sequence.translate(_COMPLEMENT)[::-1]


def _coding_sequence_matches_source(expected: str, observed: str) -> bool:
    """Accept only Pyrodigal's lossy conversion of source ambiguities to ``N``."""

    normalized = observed.upper()
    if len(normalized) != len(expected) or _DNA.fullmatch(normalized) is None:
        return False
    return all(
        actual == source or (actual == "N" and source not in _UNAMBIGUOUS_DNA)
        for source, actual in zip(expected, normalized, strict=True)
    )


def _sequence_record(
    *, key: str, label: str, molecule: str, sequence: str, orientation: str
) -> dict[str, Any]:
    pattern = _PROTEIN if molecule == "protein" else _DNA
    normalized = sequence.upper()
    if not normalized or pattern.fullmatch(normalized) is None:
        raise ExportError(f"invalid {molecule} sequence in interactive result")
    return {
        "key": key,
        "label": label,
        "molecule": molecule,
        "orientation": orientation,
        "length": len(normalized.rstrip("*")) if molecule == "protein" else len(normalized),
        "sha256": _sha256_text(normalized),
        "sequence": normalized,
    }


def _finite(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return value
    return None


def _prediction_evidence(row: Mapping[str, Any]) -> dict[str, Any]:
    evidence = row.get("evidence")
    source = evidence if isinstance(evidence, Mapping) else {}
    profile_hits = source.get("profile_hits")
    threshold = _finite(source.get("decision_threshold"))
    report_evalue = _finite(source.get("report_evalue"))
    model_id = source.get("model_id")
    if (
        not isinstance(model_id, str)
        or not model_id
        or isinstance(profile_hits, bool)
        or not isinstance(profile_hits, int)
        or profile_hits < 0
        or threshold is None
        or report_evalue is None
        or float(report_evalue) < 0
        or source.get("positive_profile_required") is not True
    ):
        raise ExportError("Cas protein decision evidence is unavailable for export")
    return {
        "model_id": model_id[:200],
        "profile_hits": profile_hits,
        "decision_threshold": threshold,
        "report_evalue": report_evalue,
        "positive_profile_required": True,
    }


def _genome_features(
    input_path: Path,
    result_root: Path,
    validated: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sources = _read_fasta(input_path, molecule="dna")
    source_by_id = {str(record["id"]): record for record in sources}
    raw_proteins = _read_jsonl(
        result_root / "casandra" / "proteins.jsonl", maximum=_MAX_RESULT_ROWS
    )
    protein_by_id = {str(row.get("protein_id") or ""): row for row in raw_proteins}
    if "" in protein_by_id or len(protein_by_id) != len(raw_proteins):
        raise ExportError("CasAndra protein identifiers are not unique for export")

    features: list[dict[str, Any]] = []
    for index, view in enumerate(validated.get("cas_proteins", [])):
        if not isinstance(view, Mapping):
            raise ExportError("validated Cas protein projection is invalid")
        protein_id = str(view.get("protein_id") or "")
        source_id = str(view.get("contig_id") or "")
        raw = protein_by_id.get(protein_id)
        source = source_by_id.get(source_id)
        start = view.get("start")
        end = view.get("end")
        strand = str(view.get("strand") or ".")
        if (
            raw is None
            or source is None
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not 1 <= start <= end <= int(source["length"])
            or raw.get("contig_id") != source_id
            or raw.get("start_1based") != start
            or raw.get("end_1based_inclusive") != end
            or str(raw.get("strand") or ".") != strand
        ):
            raise ExportError("Cas gene details disagree with validated coordinates")
        source_forward = str(source["sequence"])[start - 1 : end]
        expected_coding = _reverse_complement(source_forward) if strand == "-" else source_forward
        coding = raw.get("nucleotide_sequence")
        protein = raw.get("protein_sequence")
        if (
            not isinstance(coding, str)
            or not _coding_sequence_matches_source(expected_coding, coding)
            or not isinstance(protein, str)
            or not protein
        ):
            raise ExportError("Cas gene sequence disagrees with its validated source interval")
        coding = coding.upper()
        protein = protein.upper()
        if (
            raw.get("nucleotide_sha256") is not None
            and raw.get("nucleotide_sha256") != _sha256_text(coding)
        ) or (
            raw.get("protein_sha256") is not None
            and raw.get("protein_sha256") != _sha256_text(protein)
        ):
            raise ExportError("Cas gene sequence checksum is invalid")
        if raw.get("protein_length") is not None and raw.get("protein_length") != len(
            protein.rstrip("*")
        ):
            raise ExportError("Cas protein length is invalid")
        prediction = raw.get("prediction")
        prediction = prediction if isinstance(prediction, Mapping) else {}
        family = prediction.get("cas_family")
        result = prediction.get("result")
        profile = prediction.get("best_positive_profile")
        if (
            prediction.get("is_cas") is not True
            or not isinstance(family, str)
            or not family
            or result != family
            or not isinstance(profile, str)
            or not profile
            or prediction.get("sequence_length") != len(protein)
            or view.get("cas_family") != family
            or view.get("profile") != profile
        ):
            raise ExportError("Cas gene annotation disagrees with its validated result")
        feature = {
            **dict(view),
            "kind": "cas_gene",
            "feature_ref": f"cas_gene:{protein_id}",
            "feature_id": protein_id,
            "input_index": index,
            "result": family,
            "cas_family": family,
            "is_cas": True,
            "evidence": _prediction_evidence(prediction),
            "sequences": [
                _sequence_record(
                    key="protein",
                    label="Translated Cas protein",
                    molecule="protein",
                    sequence=protein,
                    orientation="translated_coding_strand",
                ),
                _sequence_record(
                    key="coding_dna",
                    label="Coding DNA",
                    molecule="dna",
                    sequence=coding,
                    orientation="coding_strand_5_to_3",
                ),
                _sequence_record(
                    key="source_forward_dna",
                    label="Source-forward DNA",
                    molecule="dna",
                    sequence=source_forward,
                    orientation="submitted_source_forward",
                ),
            ],
        }
        features.append(feature)

    arrays = validated.get("crispr_arrays", [])
    expected_array_keys = {
        (str(view.get("contig_id") or ""), str(view.get("array_id") or ""))
        for view in arrays
        if isinstance(view, Mapping)
    }
    raw_arrays = _raw_array_details(result_root, expected_array_keys)
    for view in arrays:
        if not isinstance(view, Mapping):
            raise ExportError("validated CRISPR array projection is invalid")
        source_id = str(view.get("contig_id") or "")
        array_id = str(view.get("array_id") or "")
        source = source_by_id.get(source_id)
        raw = raw_arrays.get((source_id, array_id))
        start = view.get("start")
        end = view.get("end")
        strand = view.get("strand")
        if (
            raw is None
            or source is None
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not 1 <= start <= end <= int(source["length"])
        ):
            raise ExportError("CRISPR array details disagree with validated coordinates")
        if (
            raw.get("category") != view.get("category")
            or raw.get("start") != start
            or raw.get("end") != end
            or raw.get("strand") != strand
        ):
            raise ExportError("CRISPR array detail disagrees with its validated report")
        source_forward = str(source["sequence"])[start - 1 : end]
        oriented = _reverse_complement(source_forward) if strand == "-" else source_forward
        consensus = raw.get("consensus_repeat")
        spacers = raw.get("spacers") if isinstance(raw.get("spacers"), list) else []
        if (
            not isinstance(consensus, str)
            or not consensus
            or view.get("spacer_count") != raw.get("reported_spacer_count")
        ):
            raise ExportError("CRISPR repeat or spacer detail is incomplete")
        sequences = [
            _sequence_record(
                key="array_source_forward",
                label="Array interval on submitted source",
                molecule="dna",
                sequence=source_forward,
                orientation="submitted_source_forward",
            )
        ]
        if strand == "-":
            sequences.append(
                _sequence_record(
                    key="array_predicted_orientation",
                    label="Array in predicted orientation",
                    molecule="dna",
                    sequence=oriented,
                    orientation="predicted_orientation_5_to_3",
                )
            )
        if isinstance(consensus, str) and consensus:
            sequences.append(
                _sequence_record(
                    key="consensus_repeat",
                    label="Consensus repeat",
                    molecule="dna",
                    sequence=consensus,
                    orientation="reported_by_crispridentify",
                )
            )
        spacer_indices = raw.get("spacer_indices", [])
        for position, spacer in enumerate(spacers):
            if not isinstance(spacer, str) or not spacer:
                continue
            spacer_index = (
                spacer_indices[position] if position < len(spacer_indices) else position + 1
            )
            sequences.append(
                _sequence_record(
                    key=f"spacer_{spacer_index}",
                    label=f"Spacer {spacer_index}",
                    molecule="dna",
                    sequence=spacer,
                    orientation="reported_array_order",
                )
            )
        features.append(
            {
                **dict(view),
                "kind": "crispr_array",
                "feature_ref": f"crispr_array:{source_id}:{array_id}",
                "feature_id": array_id,
                "result": view.get("category") or "CRISPR array",
                "consensus_repeat": consensus if isinstance(consensus, str) else None,
                "spacers": spacers,
                "spacer_indices": raw.get("spacer_indices", []),
                "omitted_empty_spacers": raw.get("omitted_empty_spacers", 0),
                "sequences": sequences,
            }
        )

    for view in validated.get("cassettes", []):
        if not isinstance(view, Mapping):
            raise ExportError("validated cassette projection is invalid")
        features.append(
            {
                **dict(view),
                "kind": "cassette",
                "feature_ref": f"cassette:{view.get('cassette_id') or ''}",
                "feature_id": str(view.get("cassette_id") or ""),
                "result": view.get("subtype") or view.get("type") or "unclassified",
                "sequences": [],
            }
        )
    return sources, features


def _raw_array_details(
    result_root: Path, expected_keys: set[tuple[str, str]]
) -> dict[tuple[str, str], dict[str, Any]]:
    details: dict[tuple[str, str], dict[str, Any]] = {}
    reports_root = result_root / "identify" / "crispridentify"
    if not reports_root.is_dir():
        return details
    report_paths = sorted(reports_root.rglob("report.json"))
    if len(report_paths) > _MAX_REPORTS:
        raise ExportError("too many CRISPRidentify reports for export")
    for path in report_paths:
        document = _read_json(path)
        source = document.get("source")
        source = source if isinstance(source, Mapping) else {}
        source_id = str(source.get("id") or "")
        arrays = document.get("arrays")
        if not source_id or not isinstance(arrays, list):
            raise ExportError("canonical CRISPRidentify details are unavailable")
        for raw in arrays:
            if not isinstance(raw, Mapping):
                raise ExportError("canonical CRISPRidentify array detail is invalid")
            array_id = str(raw.get("id") or "")
            key = (source_id, array_id)
            if not array_id or key in details:
                raise ExportError("canonical CRISPRidentify array identifier is invalid")
            if key not in expected_keys:
                continue
            consensus = raw.get("consensus_repeat")
            if consensus is not None and (
                not isinstance(consensus, str)
                or not consensus
                or _DNA.fullmatch(consensus.upper()) is None
            ):
                raise ExportError("CRISPR consensus repeat is invalid")
            spacers: list[str] = []
            spacer_indices: list[int] = []
            omitted_empty_spacers = 0
            raw_spacers = raw.get("spacers")
            if raw_spacers is not None:
                if not isinstance(raw_spacers, list) or len(raw_spacers) > _MAX_SPACERS_PER_ARRAY:
                    raise ExportError("CRISPR spacer collection is invalid")
                for position, item in enumerate(raw_spacers, start=1):
                    sequence = item.get("sequence") if isinstance(item, Mapping) else item
                    reported_index = item.get("index") if isinstance(item, Mapping) else position
                    if (
                        isinstance(reported_index, bool)
                        or not isinstance(reported_index, int)
                        or reported_index != position
                    ):
                        raise ExportError("CRISPR spacer order is invalid")
                    if sequence in {None, ""}:
                        omitted_empty_spacers += 1
                        continue
                    if not isinstance(sequence, str) or _DNA.fullmatch(sequence.upper()) is None:
                        raise ExportError("CRISPR spacer sequence is invalid")
                    spacers.append(sequence.upper())
                    spacer_indices.append(position)
            interval = raw.get("source_interval")
            interval = interval if isinstance(interval, Mapping) else {}
            orientation = raw.get("orientation")
            orientation = orientation if isinstance(orientation, Mapping) else {}
            details[key] = {
                "consensus_repeat": consensus.upper() if isinstance(consensus, str) else None,
                "spacers": spacers,
                "spacer_indices": spacer_indices,
                "reported_spacer_count": len(raw_spacers or []),
                "omitted_empty_spacers": omitted_empty_spacers,
                "category": raw.get("category"),
                "start": interval.get("start"),
                "end": interval.get("end"),
                "strand": orientation.get("strand"),
            }
    if set(details) != expected_keys:
        raise ExportError("canonical CRISPRidentify details are incomplete")
    return details


def _protein_features(
    input_path: Path, summary: Mapping[str, Any], *, include_cassette: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sources = _read_fasta(input_path, molecule="protein")
    predictions = summary.get("protein_predictions")
    if not isinstance(predictions, list) or len(predictions) != len(sources):
        raise ExportError("protein result count disagrees with normalized FASTA")
    features: list[dict[str, Any]] = []
    for index, (source, prediction) in enumerate(zip(sources, predictions, strict=True)):
        if not isinstance(prediction, Mapping) or prediction.get("protein_id") != source["id"]:
            raise ExportError("protein result order disagrees with normalized FASTA")
        features.append(
            {
                **dict(prediction),
                "kind": "protein",
                "feature_ref": f"protein:{index}:{source['id']}",
                "feature_id": str(source["id"]),
                "input_index": index,
                "sequences": [
                    _sequence_record(
                        key="protein",
                        label="Submitted protein",
                        molecule="protein",
                        sequence=str(source["sequence"]),
                        orientation="submitted_fasta_order",
                    )
                ],
            }
        )
    if include_cassette:
        cassette = summary.get("cassette_classification")
        if not isinstance(cassette, Mapping):
            raise ExportError("cassette classification is unavailable for export")
        features.append(
            {
                **dict(cassette),
                "kind": "cassette",
                "feature_ref": "cassette:supplied-cassette",
                "feature_id": "supplied-cassette",
                "sequences": [],
            }
        )
    return sources, features


def _csv_safe(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ExportError("CSV export contains a non-finite number")
        return value
    original = str(value)
    rendered = "".join(
        " " if ord(character) < 32 or ord(character) == 127 else character for character in original
    )
    formula_probe = original
    while formula_probe and (
        formula_probe[0].isspace()
        or formula_probe[0] == "\ufeff"
        or ord(formula_probe[0]) < 32
        or ord(formula_probe[0]) == 127
    ):
        formula_probe = formula_probe[1:]
    if formula_probe.startswith(("=", "+", "-", "@")):
        return "'" + rendered
    return rendered


def _csv_rows(features: Iterable[Mapping[str, Any]]) -> Iterable[dict[str, object]]:
    for feature in features:
        cas_family = feature.get("cas_family")
        if feature.get("kind") not in {"cas_gene", "protein"}:
            cas_family = None
        yield {
            field: _csv_safe(
                {
                    "feature_kind": feature.get("kind"),
                    "feature_ref": feature.get("feature_ref"),
                    "feature_id": feature.get("feature_id"),
                    "sequence_id": feature.get("protein_id") or feature.get("sequence_id"),
                    "cas_family": cas_family,
                }.get(field, feature.get(field))
            )
            for field in _CSV_FIELDS
        }


def _write_csv(path: Path, features: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS, dialect="excel")
        writer.writeheader()
        writer.writerows(_csv_rows(features))
    os.chmod(path, 0o600)


def _header_token(value: object) -> str:
    rendered = str(value or "unknown")
    return quote(
        rendered, safe="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:|=+-"
    )


def _fasta_text(records: Iterable[tuple[str, str, Mapping[str, object]]]) -> str:
    lines: list[str] = []
    for identifier, sequence, metadata in records:
        attributes = " ".join(
            f"{_header_token(key)}={_header_token(value)}"
            for key, value in metadata.items()
            if value not in {None, ""}
        )
        lines.append(f">{_header_token(identifier)}{(' ' + attributes) if attributes else ''}")
        lines.extend(sequence[offset : offset + 80] for offset in range(0, len(sequence), 80))
    return "\n".join(lines) + ("\n" if lines else "")


def _sequence(features: Iterable[Mapping[str, Any]], key: str) -> str | None:
    for feature in features:
        sequences = feature.get("sequences")
        if not isinstance(sequences, list):
            continue
        for sequence in sequences:
            if isinstance(sequence, Mapping) and sequence.get("key") == key:
                value = sequence.get("sequence")
                return value if isinstance(value, str) else None
    return None


def _write_fasta_exports(
    export_root: Path, analysis_mode: str, features: list[dict[str, Any]]
) -> None:
    if analysis_mode in {"complete_genome", "metagenomic"}:
        genes = [feature for feature in features if feature.get("kind") == "cas_gene"]
        protein_records = []
        coding_records = []
        for feature in genes:
            feature_id = str(feature["feature_id"])
            metadata = {
                "kind": "cas_gene",
                "result": feature.get("result"),
                "contig": feature.get("contig_id"),
                "loc": f"{feature.get('start')}-{feature.get('end')}",
                "strand": feature.get("strand"),
            }
            protein = _sequence([feature], "protein")
            coding = _sequence([feature], "coding_dna")
            if protein is None or coding is None:
                raise ExportError("Cas gene FASTA sequence is unavailable")
            protein_records.append((feature_id, protein, metadata))
            coding_records.append((feature_id, coding, metadata))
        _write_private_text(export_root / "cas-proteins.faa", _fasta_text(protein_records))
        _write_private_text(export_root / "cas-coding-sequences.fna", _fasta_text(coding_records))

        arrays = [feature for feature in features if feature.get("kind") == "crispr_array"]
        if arrays:
            array_records = []
            component_records = []
            for feature in arrays:
                feature_id = str(feature["feature_id"])
                sequence = _sequence([feature], "array_source_forward")
                if sequence is None:
                    raise ExportError("CRISPR array FASTA sequence is unavailable")
                array_records.append(
                    (
                        feature_id,
                        sequence,
                        {
                            "kind": "crispr_array",
                            "category": feature.get("category"),
                            "contig": feature.get("contig_id"),
                            "loc": f"{feature.get('start')}-{feature.get('end')}",
                            "strand": feature.get("strand"),
                            "orientation": "source_forward",
                        },
                    )
                )
                consensus = feature.get("consensus_repeat")
                if isinstance(consensus, str) and consensus:
                    component_records.append(
                        (
                            f"{feature_id}|consensus_repeat",
                            consensus,
                            {"kind": "consensus_repeat", "array": feature_id},
                        )
                    )
                spacer_indices = feature.get("spacer_indices") or []
                for position, spacer in enumerate(feature.get("spacers") or []):
                    spacer_index = (
                        spacer_indices[position] if position < len(spacer_indices) else position + 1
                    )
                    component_records.append(
                        (
                            f"{feature_id}|spacer={spacer_index}",
                            str(spacer),
                            {"kind": "spacer", "array": feature_id, "order": spacer_index},
                        )
                    )
            _write_private_text(export_root / "crispr-arrays.fna", _fasta_text(array_records))
            _write_private_text(
                export_root / "crispr-components.fna", _fasta_text(component_records)
            )
        return

    proteins = [feature for feature in features if feature.get("kind") == "protein"]
    all_records = []
    cas_records = []
    for feature in proteins:
        sequence = _sequence([feature], "protein")
        if sequence is None:
            raise ExportError("submitted protein FASTA sequence is unavailable")
        record = (
            str(feature["feature_id"]),
            sequence,
            {
                "result": feature.get("result"),
                "type": feature.get("type"),
                "subtype": feature.get("subtype"),
                "input_index": int(feature.get("input_index") or 0) + 1,
            },
        )
        all_records.append(record)
        if feature.get("is_cas") is True:
            cas_records.append(record)
    if analysis_mode == "classify_cassette":
        all_name = "cassette-proteins.faa"
        cas_name = "cassette-cas-proteins.faa"
    else:
        all_name = "all-proteins.faa"
        cas_name = "cas-proteins.faa"
    _write_private_text(export_root / all_name, _fasta_text(all_records))
    _write_private_text(export_root / cas_name, _fasta_text(cas_records))


def build_result_exports(
    job_root: Path,
    result_root: Path,
    *,
    analysis_mode: str,
    summary: Mapping[str, Any],
    validated_features: Mapping[str, Any] | None = None,
) -> None:
    """Write complete JSON/CSV/FASTA exports after scientific validation."""

    if analysis_mode in {"complete_genome", "metagenomic"}:
        sources, features = _genome_features(
            job_root / "input" / "genome.fasta",
            result_root,
            validated_features or {},
        )
        coordinates = "1-based-end-inclusive-source-forward"
    elif analysis_mode in {"annotate_cas_genes", "classify_cassette"}:
        sources, features = _protein_features(
            job_root / "input" / "proteins.faa",
            summary,
            include_cassette=analysis_mode == "classify_cassette",
        )
        coordinates = None
    else:
        raise ExportError("unsupported analysis mode for result export")

    feature_counts: dict[str, int] = {}
    for feature in features:
        kind = str(feature.get("kind") or "unknown")
        feature_counts[kind] = feature_counts.get(kind, 0) + 1
    payload = {
        "schema_version": "1.0.0",
        "analysis_mode": analysis_mode,
        "coordinates": coordinates,
        "feature_count": len(features),
        "feature_counts": feature_counts,
        "summary": dict(summary),
        "sources": [
            {
                "id": source["id"],
                "length": source["length"],
                "sha256": source["sha256"],
                "molecule": "protein"
                if analysis_mode in {"annotate_cas_genes", "classify_cassette"}
                else "dna",
            }
            for source in sources
        ],
        "features": features,
    }
    export_root = result_root / "exports"
    if export_root.exists():
        raise ExportError("result export directory already exists")
    staging = Path(tempfile.mkdtemp(prefix=".exports.", dir=result_root))
    os.chmod(staging, 0o700)
    try:
        _write_private_text(
            staging / "casandra-results.json",
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        )
        _write_csv(staging / "casandra-results.csv", features)
        _write_fasta_exports(staging, analysis_mode, features)
        staging.replace(export_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

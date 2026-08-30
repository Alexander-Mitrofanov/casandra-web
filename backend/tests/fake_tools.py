from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_DNA_COMPLEMENT = str.maketrans("ACGTRYSWKMBDHVN", "TGCAYRSWMKVHDBN")


def reverse_complement(sequence: str) -> str:
    return sequence.translate(_DNA_COMPLEMENT)[::-1]


def read_fasta(path: Path) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    current: str | None = None
    parts: list[str] = []
    for raw in path.read_text(encoding="ascii").splitlines():
        if raw.startswith(">"):
            if current is not None:
                records.append((current, "".join(parts)))
            current = raw[1:].split()[0]
            parts = []
        elif raw.strip():
            parts.append(raw.strip())
    if current is not None:
        records.append((current, "".join(parts)))
    return records


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def protein_prediction(protein_id: str, sequence: str) -> dict[str, object]:
    is_cas = not protein_id.lower().startswith("noncas")
    family_only = protein_id.startswith(
        ("cas2_without_type", "cas4_without_type", "csx32_without_type")
    )
    if protein_id.startswith("cas2_without_type"):
        profile, family = "C25_Cas2_1", "Cas2"
    elif protein_id.startswith("cas4_without_type"):
        profile, family = "C25_Cas4_1", "Cas4"
    elif protein_id.startswith("csx32_without_type"):
        profile, family = "C25_Csx32_1", "Csx32"
    else:
        profile, family = "C25_Cas3_1", "Cas3"
    if protein_id == "annotation_missing_family":
        family = None
    prediction = {
        "sequence_id": protein_id,
        "sequence_length": len(sequence),
        "is_cas": is_cas,
        "classification": (
            {"class": "1", "type": "I", "subtype": "I-E"}
            if is_cas and not family_only
            else {"class": None, "type": None, "subtype": None}
        ),
        "best_positive_profile": profile if is_cas else None,
        "cas_family": family if is_cas else None,
        "result": family if is_cas else "no cas",
        "positive_profile_score": 42.0 if is_cas else -10.0,
        "hard_negative_profile_score": 2.0,
        "score_margin": 40.0 if is_cas else -12.0,
        "evidence": {
            "model_id": "fake-protein-model",
            "profile_hits": 1 if is_cas else 0,
            "decision_threshold": 0.0,
            "positive_profile_required": True,
            "report_evalue": 0.001,
        },
    }
    if protein_id == "annotation_missing_result":
        prediction.pop("result")
    elif protein_id == "annotation_bad_result":
        prediction["result"] = "no cas"
    return prediction


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def predict_proteins(input_path: Path, output: Path) -> int:
    predictions = [
        protein_prediction(protein_id, sequence) for protein_id, sequence in read_fasta(input_path)
    ]
    write_jsonl(output, predictions)
    return 0


def annotate_proteins(input_path: Path, output: Path) -> int:
    records = read_fasta(input_path)
    input_ids = [protein_id for protein_id, _sequence in records]
    predictions = [protein_prediction(protein_id, sequence) for protein_id, sequence in records]
    output.mkdir(parents=True)
    predictions_path = output / "protein_predictions.jsonl"
    write_jsonl(predictions_path, predictions)
    cas_count = sum(row["is_cas"] is True for row in predictions)
    write_json(
        output / "run.json",
        {
            "schema_version": 1,
            "program": "CasAndra",
            "program_version": "0.3.0.dev0",
            "analysis": "annotate_cas_genes",
            "bundle_id": "fake-bundle",
            "bundle_role": "deployment_refit",
            "bundle_manifest_sha256": "a" * 64,
            "model_id": (
                "mismatched-fake-model"
                if "annotation_model_mismatch" in input_ids
                else "fake-protein-model"
            ),
            "inputs": [
                {
                    "kind": "protein_fasta",
                    "name": input_path.name,
                    "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                }
            ],
            "cpu_threads": 1,
            "wall_seconds": 0.02,
            "protein_records": len(input_ids),
            "cas_proteins": cas_count,
            "non_cas_proteins": len(input_ids) - cas_count,
            "result_contract": {"positive": "cas_family", "negative": "no cas"},
            "crispr_array_prediction": False,
            "offline_inference": True,
        },
    )
    manifest_files = {}
    for path in sorted(output.iterdir()):
        if path.is_file():
            manifest_files[path.name] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
            }
    write_json(
        output / "manifest.json",
        {"schema_version": 1, "bundle_manifest_sha256": "a" * 64, "files": manifest_files},
    )
    if "annotation_checksum_mismatch" in input_ids:
        predictions_path.write_text(
            predictions_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
        )
    return 0


def classify_cassette(input_path: Path, output: Path) -> int:
    records = read_fasta(input_path)
    predictions = [protein_prediction(protein_id, sequence) for protein_id, sequence in records]
    output.mkdir(parents=True)
    write_jsonl(output / "proteins.jsonl", predictions)
    input_ids = [protein_id for protein_id, _sequence in records]
    cas_ids = [str(row["sequence_id"]) for row in predictions if row["is_cas"]]
    non_cas_ids = [value for value in input_ids if value not in set(cas_ids)]
    final = {
        "class": "1" if cas_ids else None,
        "type": "I" if cas_ids else None,
        "subtype": "I-E" if cas_ids else None,
        "method": "direct_profile_aggregation",
        "confidence": 1.0 if cas_ids else 0.0,
        "direct_profile_result": {},
    }
    write_json(
        output / "cassette.json",
        {
            "schema_version": 1,
            "cassette_id": "supplied-cassette",
            "input_mode": "ordered_protein_fasta",
            "input_protein_ids": input_ids,
            "cas_protein_ids": cas_ids,
            "non_cas_protein_ids": non_cas_ids,
            "protein_count": len(input_ids),
            "cas_protein_count": len(cas_ids),
            "classification": final,
            "direct_profile_classification": {},
            "order_used_for_architecture": True,
            "coordinates_available": False,
            "crispr_array_evidence_used": False,
        },
    )
    run = {
        "schema_version": 1,
        "program": "CasAndra",
        "program_version": "0.3.0.dev0",
        "analysis": "classify_cassette",
        "bundle_id": "fake-bundle",
        "bundle_role": "deployment_refit",
        "bundle_manifest_sha256": "a" * 64,
        "model_id": (
            "mismatched-fake-model" if "model_mismatch" in input_ids else "fake-protein-model"
        ),
        "inputs": [
            {
                "kind": "protein_fasta",
                "name": input_path.name,
                "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
            }
        ],
        "protein_records": len(input_ids),
        "cas_proteins": len(cas_ids),
        "classification": {
            name: final[name] for name in ("class", "type", "subtype", "method", "confidence")
        },
        "wall_seconds": 0.01,
        "crispr_array_prediction": False,
        "offline_inference": True,
    }
    if "cassette_missing_bundle_id" in input_ids:
        run["bundle_id"] = ""
    if "cassette_missing_bundle_role" in input_ids:
        run["bundle_role"] = ""
    if "cassette_bad_program" in input_ids:
        run["program"] = "not-CasAndra"
    if "cassette_bad_program_version" in input_ids:
        run["program_version"] = "0.0.0"
    if "cassette_bundle_mismatch" in input_ids:
        run["bundle_manifest_sha256"] = "b" * 64
    if "cassette_input_kind_mismatch" in input_ids:
        run["inputs"][0]["kind"] = "genome_fasta"
    if "cassette_input_name_mismatch" in input_ids:
        run["inputs"][0]["name"] = "different.faa"
    if "cassette_input_sha_mismatch" in input_ids:
        run["inputs"][0]["sha256"] = "b" * 64
    if "cassette_online_inference" in input_ids:
        run["offline_inference"] = False
    if "cassette_arrays_enabled" in input_ids:
        run["crispr_array_prediction"] = True
    if "cassette_negative_wall_time" in input_ids:
        run["wall_seconds"] = -1
    write_json(output / "run.json", run)
    manifest_files = {}
    for path in sorted(output.iterdir()):
        if path.is_file():
            manifest_files[path.name] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
            }
    write_json(
        output / "manifest.json",
        {"schema_version": 1, "bundle_manifest_sha256": "a" * 64, "files": manifest_files},
    )
    return 0


def predict_genome(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--genome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gene-mode")
    parser.add_argument("--translation-table")
    parser.add_argument("--threads")
    args = parser.parse_args(argv)
    records = read_fasta(args.genome)
    args.output.mkdir(parents=True)
    proteins = []
    cassettes = []
    for index, (source_id, sequence) in enumerate(records, start=1):
        end = min(len(sequence), 30)
        protein_id = f"{source_id}_cas1"
        protein_sequence = "MTEST"
        prediction = protein_prediction(protein_id, protein_sequence)
        reverse_source_ids = {"export_reverse_gene", "export_reverse_ambiguity"}
        strand = "-" if source_id in reverse_source_ids else "+"
        source_interval = sequence[:end]
        coding_sequence = reverse_complement(source_interval) if strand == "-" else source_interval
        if source_id == "export_reverse_ambiguity":
            coding_sequence = "".join(
                base if base in "ACGT" else "N" for base in coding_sequence
            )
        if source_id == "export_coding_mismatch":
            coding_sequence = "A" * len(source_interval)
        proteins.append(
            {
                "protein_id": protein_id,
                "contig_id": source_id,
                "start_1based": 1,
                "end_1based_inclusive": end,
                "strand": strand,
                "partial_5prime": False,
                "partial_3prime": False,
                "nucleotide_sequence": coding_sequence,
                "nucleotide_sha256": hashlib.sha256(coding_sequence.encode("ascii")).hexdigest(),
                "protein_sequence": protein_sequence,
                "protein_length": len(protein_sequence),
                "protein_sha256": hashlib.sha256(protein_sequence.encode("ascii")).hexdigest(),
                "translation_table": 11,
                "translation_policy": "caller_selected_per_gene",
                "caller": {
                    "program": "Pyrodigal",
                    "version": "3.7.1",
                    "mode": "meta" if args.gene_mode == "meta" else "single",
                    "requested_mode": args.gene_mode,
                    "translation_table": 11,
                },
                "prediction": prediction,
            }
        )
        if source_id == "rejected_profile":
            rejected_id = f"noncas_{source_id}"
            rejected_prediction = protein_prediction(rejected_id, protein_sequence)
            rejected_prediction["best_positive_profile"] = "C25_Cas12_F05_2"
            rejected_prediction["positive_profile_score"] = 4.6643548011779785
            rejected_prediction["hard_negative_profile_score"] = 17.103843688964844
            rejected_prediction["score_margin"] = -12.439488887786865
            proteins.append(
                {
                    **proteins[-1],
                    "protein_id": rejected_id,
                    "prediction": rejected_prediction,
                }
            )
        cassette_id = f"casandra|contig={source_id}|cassette={index:04d}|loc=1-{end}"
        cassettes.append(
            {
                "cassette_id": cassette_id,
                "contig_id": source_id,
                "start_1based": 1,
                "end_1based_inclusive": end,
                "cas_gene_count": 1,
                "cas_protein_ids": [protein_id],
                "final_classification": {
                    "class": "1",
                    "type": "I",
                    "subtype": "I-E",
                    "method": "direct_profile_aggregation",
                    "confidence": 1.0,
                },
                "genome_evidence_gate": {"accepted": True, "rule": "test_gate"},
            }
        )
    for name, rows in (("proteins.jsonl", proteins), ("cassettes.jsonl", cassettes)):
        with (args.output / name).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    (args.output / "cas_proteins.tsv").write_text(
        "protein_id\tcontig\n"
        + "\n".join(
            f"{row['protein_id']}\t{row['contig_id']}"
            for row in proteins
            if row["prediction"]["is_cas"] is True
        )
        + "\n",
        encoding="utf-8",
    )
    (args.output / "cassettes.tsv").write_text(
        "cassette_id\tcontig\n"
        + "\n".join(f"{row['cassette_id']}\t{row['contig_id']}" for row in cassettes)
        + "\n",
        encoding="utf-8",
    )
    (args.output / "casandra.gff3").write_text("##gff-version 3\n", encoding="utf-8")
    write_json(
        args.output / "run.json",
        {
            "schema_version": 5,
            "program": "CasAndra",
            "program_version": "0.3.0.dev0",
            "bundle_id": "fake-bundle",
            "bundle_role": "deployment_refit",
            "inputs": [
                {
                    "kind": "genome_fasta",
                    "name": args.genome.name,
                    "sha256": hashlib.sha256(args.genome.read_bytes()).hexdigest(),
                }
            ],
            "genes": len(proteins),
            "cas_proteins": sum(row["prediction"]["is_cas"] is True for row in proteins),
            "cas_cassettes": len(cassettes),
            "wall_seconds": 0.01,
        },
    )
    manifest_files = {}
    for path in sorted(args.output.rglob("*")):
        if path.is_file():
            manifest_files[str(path.relative_to(args.output))] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
            }
    write_json(
        args.output / "manifest.json",
        {"schema_version": 5, "bundle_manifest_sha256": "a" * 64, "files": manifest_files},
    )
    return 0


def casandra(argv: list[str]) -> int:
    command, *arguments = argv
    if command == "predict-genome":
        return predict_genome(arguments)
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads")
    args = parser.parse_args(arguments)
    if command == "predict-proteins":
        return predict_proteins(args.input, args.output)
    if command == "annotate-proteins":
        return annotate_proteins(args.input, args.output)
    if command == "classify-cassette":
        return classify_cassette(args.input, args.output)
    return 2


def identify(argv: list[str]) -> int:
    if len(argv) < 3 or argv[0] != "run":
        return 2
    records_root = Path(argv[1])
    output = Path(argv[2])
    output.mkdir(parents=True)
    arrays = []
    for fasta in sorted(records_root.glob("*.fasta")):
        source_id, sequence = read_fasta(fasta)[0]
        end = min(8, len(sequence))
        array = {
            "id": " =2+5" if source_id == "csv_formula" else f"CRISPR-{source_id}",
            "category": "Bona-fide",
            "certainty_score": 0.81,
            "orientation": {"strand": "+"},
            "repeat_count": 3,
            "spacer_count": 2,
            "consensus_repeat": "ACGT",
            "spacers": [
                {"index": 1, "sequence": "CGTA"},
                {"index": 2, "sequence": "GTAC"},
            ],
            "source_interval": {"start": 2, "end": end, "length": end - 1},
            "validation": {
                "status": "valid",
                "source_reconstructed": True,
                "method": "independent_original_sequence_slicing",
            },
        }
        arrays.append(array)
        write_json(
            output / "crispridentify" / fasta.stem / "report.json",
            {
                "schema": {"name": "CRISPRidentify-report", "version": "1.1.0"},
                "coordinate_system": {
                    "indexing": 1,
                    "end_inclusive": True,
                    "reference": "input_forward_strand",
                    "orientation_is_separate": True,
                },
                "source": {
                    "id": source_id,
                    "length": len(sequence),
                    "sha256": hashlib.sha256(sequence.upper().encode("ascii")).hexdigest(),
                    "sha256_scope": "uppercase_sequence",
                },
                "summary": {
                    "array_count": 1,
                    "accepted_array_count": 1,
                    "category_counts": {
                        "Bona-fide": 1,
                        "Possible": 0,
                        "Low score": 0,
                    },
                },
                "validation": {
                    "status": "valid",
                    "method": "independent_original_sequence_slicing",
                    "validated_array_count": 1,
                    "invalid_array_count": 0,
                },
                "arrays": [array],
            },
        )
    write_json(
        output / "adapter" / "manifest.json",
        {"schema_version": "1.0.0", "source_binding": "verified", "arrays": len(arrays)},
    )
    write_json(
        output / "integration_result.json",
        {
            "schema": {"name": "crispr-tool-integration-run", "version": "1.0.0"},
            "status": "completed",
            "stages": {"crispridentify": {"status": "completed"}},
        },
    )
    return 0


if __name__ == "__main__":
    mode, *arguments = sys.argv[1:]
    raise SystemExit(casandra(arguments) if mode == "casandra" else identify(arguments))

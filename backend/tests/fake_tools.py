from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


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


def casandra(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
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
        prediction = {
            "sequence_id": protein_id,
            "is_cas": True,
            "classification": {"class": "1", "type": "I", "subtype": "I-E"},
            "best_positive_profile": "Cas3",
            "positive_profile_score": 42.0,
            "score_margin": 12.5,
        }
        proteins.append(
            {
                "protein_id": protein_id,
                "contig_id": source_id,
                "start_1based": 1,
                "end_1based_inclusive": end,
                "strand": "+",
                "partial_5prime": False,
                "partial_3prime": False,
                "protein_sequence": "MTEST",
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
        + "\n".join(f"{row['protein_id']}\t{row['contig_id']}" for row in proteins)
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
            "cas_proteins": len(proteins),
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
            "id": f"CRISPR-{source_id}",
            "category": "Bona-fide",
            "certainty_score": 0.81,
            "orientation": {"strand": "+"},
            "repeat_count": 3,
            "spacer_count": 2,
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

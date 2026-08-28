#!/usr/bin/env python3
"""Generate the frozen CasAndra example FASTA inputs from one RefSeq record."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from Bio import SeqIO

REFERENCE_ACCESSION = "NC_002737.2"
COMPLETE_INTERVAL = (845_001, 870_000)
METAGENOMIC_INTERVALS = (
    ("type_IIA_locus", 850_001, 863_000),
    ("type_IC_locus", 1_282_001, 1_293_000),
)
CASSETTE_GENES = ("cas9", "cas1", "cas2", "csn2")
ANNOTATION_GENES = (*CASSETTE_GENES, "lepA")


def wrap(sequence: str, width: int = 80) -> str:
    return "\n".join(
        sequence[offset : offset + width] for offset in range(0, len(sequence), width)
    )


def nucleotide_record(record, label: str, start: int, end: int) -> str:
    sequence = str(record.seq[start - 1 : end]).upper()
    return f">{label} {REFERENCE_ACCESSION}:{start}-{end}\n{wrap(sequence)}\n"


def translated_features(record) -> dict[str, tuple[str, str, int, int]]:
    selected: dict[str, tuple[str, str, int, int]] = {}
    for feature in record.features:
        if feature.type != "CDS" or "translation" not in feature.qualifiers:
            continue
        gene = str(feature.qualifiers.get("gene", [""])[0])
        start = int(feature.location.start) + 1
        end = int(feature.location.end)
        if gene not in ANNOTATION_GENES or not 850_001 <= start <= 863_000:
            continue
        locus = str(feature.qualifiers.get("locus_tag", [gene])[0])
        sequence = (
            str(feature.qualifiers["translation"][0]).replace(" ", "").replace("\n", "")
        )
        selected[gene] = (locus, sequence, start, end)
    missing = set(ANNOTATION_GENES) - set(selected)
    if missing:
        raise RuntimeError(
            f"Reference record is missing expected CDS translations: {sorted(missing)}"
        )
    return selected


def protein_fasta(
    features: dict[str, tuple[str, str, int, int]], genes: tuple[str, ...]
) -> str:
    chunks = []
    for gene in genes:
        locus, sequence, start, end = features[gene]
        chunks.append(
            f">{locus}_{gene} {REFERENCE_ACCESSION}:{start}-{end} gene={gene}\n{wrap(sequence)}\n"
        )
    return "".join(chunks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--genbank", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()

    record = SeqIO.read(args.genbank, "genbank")
    if record.id != REFERENCE_ACCESSION:
        raise RuntimeError(f"Expected {REFERENCE_ACCESSION}, received {record.id}")
    features = translated_features(record)
    args.output_root.mkdir(parents=True, exist_ok=True)

    complete_dir = args.output_root / "complete_genome"
    annotation_dir = args.output_root / "annotate_cas_genes"
    cassette_dir = args.output_root / "classify_cassette"
    metagenomic_dir = args.output_root / "metagenomic"
    for directory in (complete_dir, annotation_dir, cassette_dir, metagenomic_dir):
        directory.mkdir(parents=True, exist_ok=True)

    complete_dir.joinpath("input.fna").write_text(
        nucleotide_record(record, "spyogenes_type_IIA_complete", *COMPLETE_INTERVAL),
        encoding="ascii",
    )
    annotation_dir.joinpath("input.faa").write_text(
        protein_fasta(features, ANNOTATION_GENES), encoding="ascii"
    )
    cassette_dir.joinpath("input.faa").write_text(
        protein_fasta(features, CASSETTE_GENES), encoding="ascii"
    )
    metagenomic_dir.joinpath("input.fna").write_text(
        "".join(
            nucleotide_record(record, f"spyogenes_{label}", start, end)
            for label, start, end in METAGENOMIC_INTERVALS
        ),
        encoding="ascii",
    )

    manifest = {
        "reference": REFERENCE_ACCESSION,
        "complete_genome_interval": COMPLETE_INTERVAL,
        "metagenomic_intervals": METAGENOMIC_INTERVALS,
        "annotation_genes": ANNOTATION_GENES,
        "cassette_genes": CASSETTE_GENES,
    }
    args.output_root.joinpath("source-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="ascii"
    )


if __name__ == "__main__":
    main()

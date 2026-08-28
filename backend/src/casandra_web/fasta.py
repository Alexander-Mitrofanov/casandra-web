"""Bounded, deterministic nucleotide FASTA normalization."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_DNA = frozenset("ACGTRYSWKMBDHVN")
_PROTEIN = frozenset("ACDEFGHIKLMNPQRSTVWYBXZJUO")
_SOURCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}")


class FastaError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FastaRecord:
    source_id: str
    sequence: str


@dataclass(frozen=True, slots=True)
class NormalizedFasta:
    data: bytes
    records: tuple[FastaRecord, ...]
    base_count: int
    sha256: str


def normalize_fasta(
    value: str,
    *,
    max_request_bytes: int,
    max_total_bases: int,
    max_record_bases: int,
    max_records: int,
    max_header_characters: int,
) -> NormalizedFasta:
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise FastaError("Input must be valid UTF-8 text") from error
    if len(encoded) > max_request_bytes:
        raise FastaError("Input exceeds the configured upload limit")
    if "\x00" in value:
        raise FastaError("Input contains a NUL byte")
    text = value.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise FastaError("Input is empty")
    if not text.startswith(">"):
        compact = "".join(text.split()).upper()
        text = f">sequence_1\n{compact}"

    records: list[FastaRecord] = []
    seen: set[str] = set()
    current_id: str | None = None
    sequence_parts: list[str] = []

    def finish() -> None:
        nonlocal current_id, sequence_parts
        if current_id is None:
            return
        sequence = "".join(sequence_parts).upper()
        if not sequence:
            raise FastaError(f"Record {current_id!r} has no sequence")
        invalid = sorted(set(sequence).difference(_DNA))
        if invalid:
            raise FastaError(
                f"Record {current_id!r} contains unsupported nucleotide symbol(s): "
                + " ".join(invalid[:8])
            )
        if len(sequence) > max_record_bases:
            raise FastaError(f"Record {current_id!r} exceeds the per-record base limit")
        records.append(FastaRecord(current_id, sequence))
        if len(records) > max_records:
            raise FastaError("Input contains too many FASTA records")

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            finish()
            header = line[1:].strip()
            if not header or len(header) > max_header_characters:
                raise FastaError("FASTA headers must be non-empty and within the configured limit")
            if any((ord(character) < 32 and character != "\t") or ord(character) == 127 for character in header):
                raise FastaError("FASTA headers cannot contain control characters")
            source_id = header.split()[0]
            if _SOURCE_ID.fullmatch(source_id) is None:
                raise FastaError(
                    "FASTA record IDs may contain only letters, digits, dot, underscore, colon, or dash"
                )
            if source_id in seen:
                raise FastaError(f"Duplicate FASTA record ID: {source_id}")
            seen.add(source_id)
            current_id = source_id
            sequence_parts = []
        else:
            if current_id is None:
                raise FastaError("Sequence data appears before the first FASTA header")
            sequence_parts.append("".join(line.split()))
    finish()
    if not records:
        raise FastaError("Input contains no FASTA records")
    base_count = sum(len(record.sequence) for record in records)
    if base_count > max_total_bases:
        raise FastaError("Input exceeds the configured total base limit")
    rendered = "".join(
        f">{record.source_id}\n"
        + "\n".join(
            record.sequence[index : index + 80] for index in range(0, len(record.sequence), 80)
        )
        + "\n"
        for record in records
    ).encode("ascii")
    return NormalizedFasta(
        data=rendered,
        records=tuple(records),
        base_count=base_count,
        sha256=hashlib.sha256(rendered).hexdigest(),
    )


def normalize_protein_fasta(
    value: str,
    *,
    max_request_bytes: int,
    max_total_residues: int,
    max_record_residues: int,
    max_records: int,
    max_header_characters: int,
) -> NormalizedFasta:
    """Normalize bounded amino-acid FASTA with at most one terminal stop symbol."""

    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise FastaError("Input must be valid UTF-8 text") from error
    if len(encoded) > max_request_bytes:
        raise FastaError("Input exceeds the configured upload limit")
    if "\x00" in value:
        raise FastaError("Input contains a NUL byte")
    text = value.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise FastaError("Input is empty")
    if not text.startswith(">"):
        text = f">sequence_1\n{''.join(text.split()).upper()}"

    records: list[FastaRecord] = []
    seen: set[str] = set()
    current_id: str | None = None
    sequence_parts: list[str] = []

    def finish() -> None:
        nonlocal current_id, sequence_parts
        if current_id is None:
            return
        sequence = "".join(sequence_parts).upper()
        if not sequence:
            raise FastaError(f"Record {current_id!r} has no sequence")
        if "*" in sequence[:-1] or sequence.count("*") > 1:
            raise FastaError(
                f"Record {current_id!r} may contain only one terminal stop symbol"
            )
        residues = sequence.removesuffix("*")
        if not residues:
            raise FastaError(f"Record {current_id!r} has no amino-acid residues")
        invalid = sorted(set(residues).difference(_PROTEIN))
        if invalid:
            raise FastaError(
                f"Record {current_id!r} contains unsupported amino-acid symbol(s): "
                + " ".join(invalid[:8])
            )
        if len(residues) > max_record_residues:
            raise FastaError(f"Record {current_id!r} exceeds the per-record residue limit")
        records.append(FastaRecord(current_id, sequence))
        if len(records) > max_records:
            raise FastaError("Input contains too many FASTA records")

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            finish()
            header = line[1:].strip()
            if not header or len(header) > max_header_characters:
                raise FastaError("FASTA headers must be non-empty and within the configured limit")
            if any(
                (ord(character) < 32 and character != "\t") or ord(character) == 127
                for character in header
            ):
                raise FastaError("FASTA headers cannot contain control characters")
            source_id = header.split()[0]
            if _SOURCE_ID.fullmatch(source_id) is None:
                raise FastaError(
                    "FASTA record IDs may contain only letters, digits, dot, underscore, colon, or dash"
                )
            if source_id in seen:
                raise FastaError(f"Duplicate FASTA record ID: {source_id}")
            seen.add(source_id)
            current_id = source_id
            sequence_parts = []
        else:
            if current_id is None:
                raise FastaError("Sequence data appears before the first FASTA header")
            sequence_parts.append("".join(line.split()))
    finish()
    if not records:
        raise FastaError("Input contains no FASTA records")
    residue_count = sum(len(record.sequence.rstrip("*")) for record in records)
    if residue_count > max_total_residues:
        raise FastaError("Input exceeds the configured total residue limit")
    rendered = "".join(
        f">{record.source_id}\n"
        + "\n".join(
            record.sequence[index : index + 80]
            for index in range(0, len(record.sequence), 80)
        )
        + "\n"
        for record in records
    ).encode("ascii")
    return NormalizedFasta(
        data=rendered,
        records=tuple(records),
        base_count=residue_count,
        sha256=hashlib.sha256(rendered).hexdigest(),
    )

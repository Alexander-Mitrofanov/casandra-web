import pytest

from casandra_web.fasta import FastaError, normalize_fasta, normalize_protein_fasta


def normalize(value: str):
    return normalize_fasta(
        value,
        max_request_bytes=10_000,
        max_total_bases=1_000,
        max_record_bases=1_000,
        max_records=5,
        max_header_characters=100,
    )


def test_raw_dna_becomes_deterministic_fasta():
    result = normalize("acgt nn\nAC")
    assert result.data == b">sequence_1\nACGTNNAC\n"
    assert result.base_count == 8
    assert result.records[0].source_id == "sequence_1"


def test_headers_are_minimized_and_records_preserved():
    result = normalize(">contig_1 private description\nACGT\n>contig-2\nNNNN\n")
    assert result.data == b">contig_1\nACGT\n>contig-2\nNNNN\n"
    assert [record.source_id for record in result.records] == ["contig_1", "contig-2"]


def test_tab_delimited_header_description_is_accepted():
    assert normalize(">contig:1\tdescription\nACGT\n").records[0].source_id == "contig:1"


def test_utf8_bom_is_ignored_consistently():
    result = normalize("\ufeff>contig:1\nACGT\n")
    assert result.data == b">contig:1\nACGT\n"


def test_nucleotide_limits_are_inclusive_at_the_exact_boundary():
    result = normalize_fasta(
        ">one\nAAAA\n",
        max_request_bytes=10,
        max_total_bases=4,
        max_record_bases=4,
        max_records=1,
        max_header_characters=100,
    )
    assert result.base_count == 4

    with pytest.raises(FastaError, match="total base limit"):
        normalize_fasta(
            ">one\nAAAAA\n",
            max_request_bytes=20,
            max_total_bases=4,
            max_record_bases=5,
            max_records=1,
            max_header_characters=100,
        )


@pytest.mark.parametrize(
    "value, message",
    [
        (">same\nACGT\n>same\nACGT", "Duplicate"),
        (">bad/id\nACGT", "record IDs"),
        (">one\nACGTZ", "unsupported"),
        (">one\n", "no sequence"),
    ],
)
def test_malformed_fasta_is_rejected(value, message):
    with pytest.raises(FastaError, match=message):
        normalize(value)


def normalize_proteins(value: str):
    return normalize_protein_fasta(
        value,
        max_request_bytes=10_000,
        max_total_residues=1_000,
        max_record_residues=1_000,
        max_records=50,
        max_header_characters=100,
    )


def test_raw_protein_and_terminal_stop_are_normalized():
    result = normalize_proteins("mktx*")
    assert result.data == b">sequence_1\nMKTX*\n"
    assert result.base_count == 4
    assert result.records[0].sequence == "MKTX*"


@pytest.mark.parametrize(
    "sequence,message",
    [
        ("M*KT", "terminal stop"),
        ("M--KT", "unsupported"),
        ("MK7T", "unsupported"),
        ("*", "no amino-acid residues"),
    ],
)
def test_invalid_protein_symbols_are_rejected(sequence, message):
    with pytest.raises(FastaError, match=message):
        normalize_proteins(f">protein\n{sequence}")

export const SAMPLE_FASTA = [
  ">NC_demo_001 complete archaeal contig",
  "ATGCGTAC".repeat(400),
  ">NODE_demo_2 fragmented metagenomic contig",
  "GGTACCAA".repeat(225),
].join("\n") + "\n";

function illustrativeSequence(key, label, molecule, length, orientation) {
  const alphabet = molecule === "protein" ? "MAGNKSTVDELRQIFPYHCW" : "ACGTTGCA";
  const sequence = alphabet.repeat(Math.ceil(length / alphabet.length)).slice(0, length);
  return { key, label, molecule, length, orientation, sequence };
}

function illustrativeGene(feature, proteinLength) {
  const dnaLength = feature.end - feature.start + 1;
  return {
    ...feature,
    kind: "cas_gene",
    feature_id: feature.protein_id,
    result: feature.profile,
    is_cas: true,
    residue_count: proteinLength,
    sequences: [
      illustrativeSequence("protein", "Translated Cas protein", "protein", proteinLength, "translated_coding_strand"),
      illustrativeSequence("coding_dna", "Coding DNA", "dna", dnaLength, "coding_strand_5_to_3"),
      illustrativeSequence("source_forward_dna", "Source-forward DNA", "dna", dnaLength, "submitted_source_forward"),
    ],
  };
}

function illustrativeArray(feature, consensusRepeat, spacers) {
  const intervalLength = feature.end - feature.start + 1;
  return {
    ...feature,
    kind: "crispr_array",
    feature_id: feature.array_id,
    result: feature.category,
    consensus_repeat: consensusRepeat,
    spacer_count: spacers.length,
    spacers,
    sequences: [
      illustrativeSequence("array_source_forward", "Array interval on submitted source", "dna", intervalLength, "submitted_source_forward"),
      { key: "consensus_repeat", label: "Consensus repeat", molecule: "dna", length: consensusRepeat.length, orientation: "reported_by_crispridentify", sequence: consensusRepeat },
      ...spacers.map((sequence, index) => ({ key: `spacer_${index + 1}`, label: `Spacer ${index + 1}`, molecule: "dna", length: sequence.length, orientation: "reported_array_order", sequence })),
    ],
  };
}

export const SAMPLE_JOB = Object.freeze({
  job_id: "sample_result_not_a_remote_job",
  status: "completed",
  phase: "completed",
  input: {
    filename: "casandra-example.fna",
    record_count: 2,
    base_count: 5000,
    source_ids: ["NC_demo_001", "NODE_demo_2"],
  },
  options: { analysis_mode: "complete_genome", include_crispr_arrays: true, gene_mode: "single", translation_table: 11, translation_table_scope: "single_mode_training_request" },
  summary: {
    schema_version: "1.1.0",
    analysis_mode: "complete_genome",
    include_crispr_arrays: true,
    overview: {
      contig_count: 2,
      total_bases: 5000,
      gene_count: 9,
      cas_protein_count: 7,
      cassette_count: 2,
      crispr_array_count: 3,
      wall_seconds: 11.8,
    },
    contigs: [
      { id: "NC_demo_001", length: 3200 },
      { id: "NODE_demo_2", length: 1800 },
    ],
    cassettes: [
      { cassette_id: "cassette_001", contig_id: "NC_demo_001", start: 620, end: 2335, cas_gene_count: 5, class: "1", type: "I", subtype: "I-E", method: "hybrid", confidence: 0.94, confidence_is_probability: false, evidence_gate: { accepted: true, rule: "genome_context" }, nearest_array: { array_id: "CRISPR_001", distance_bp: 144, interpretation: "coordinate_co_location_only" } },
      { cassette_id: "cassette_002", contig_id: "NODE_demo_2", start: 410, end: 1290, cas_gene_count: 2, class: "2", type: "V", subtype: "V-A", method: "protein", confidence: 0.78, confidence_is_probability: false, evidence_gate: { accepted: true, rule: "genome_context" }, nearest_array: { array_id: "CRISPR_003", distance_bp: 59, interpretation: "coordinate_co_location_only" } },
    ],
    cas_proteins: [
      { protein_id: "cas3_demo", contig_id: "NC_demo_001", start: 652, end: 1119, strand: "+", partial_5prime: false, partial_3prime: false, translation_table: 11, type: "I", subtype: "I-E", profile: "Cas3", score_margin: 8.42, cassette_id: "cassette_001" },
      { protein_id: "cse1_demo", contig_id: "NC_demo_001", start: 1180, end: 1440, strand: "+", partial_5prime: false, partial_3prime: false, translation_table: 11, type: "I", subtype: "I-E", profile: "Cse1", score_margin: 5.91, cassette_id: "cassette_001" },
      { protein_id: "cse2_demo", contig_id: "NC_demo_001", start: 1482, end: 1694, strand: "+", partial_5prime: false, partial_3prime: false, translation_table: 11, type: "I", subtype: "I-E", profile: "Cse2", score_margin: 4.73, cassette_id: "cassette_001" },
      { protein_id: "cas7_demo", contig_id: "NC_demo_001", start: 1741, end: 2040, strand: "+", partial_5prime: false, partial_3prime: false, translation_table: 11, type: "I", subtype: "I-E", profile: "Cas7", score_margin: 7.14, cassette_id: "cassette_001" },
      { protein_id: "cas5_demo", contig_id: "NC_demo_001", start: 2082, end: 2310, strand: "+", partial_5prime: false, partial_3prime: false, translation_table: 11, type: "I", subtype: "I-E", profile: "Cas5", score_margin: 3.82, cassette_id: "cassette_001" },
      { protein_id: "cas12a_demo", contig_id: "NODE_demo_2", start: 438, end: 1010, strand: "-", partial_5prime: true, partial_3prime: false, translation_table: 11, type: "V", subtype: "V-A", profile: "Cas12a", score_margin: 9.18, cassette_id: "cassette_002" },
      { protein_id: "cas4_demo", contig_id: "NODE_demo_2", start: 1055, end: 1272, strand: "-", partial_5prime: false, partial_3prime: false, translation_table: 11, type: "V", subtype: "V-A", profile: "Cas4", score_margin: 3.35, cassette_id: "cassette_002" },
    ],
    crispr_arrays: [
      { array_id: "CRISPR_001", contig_id: "NC_demo_001", start: 2480, end: 2898, strand: "+", category: "Bona-fide", repeat_count: 7, model_score: 0.97, model_score_is_probability: false },
      { array_id: "CRISPR_002", contig_id: "NC_demo_001", start: 210, end: 475, strand: "?", category: "Possible", repeat_count: 4, model_score: 0.64, model_score_is_probability: false },
      { array_id: "CRISPR_003", contig_id: "NODE_demo_2", start: 1350, end: 1662, strand: "-", category: "Bona-fide", repeat_count: 5, model_score: 0.91, model_score_is_probability: false },
    ],
    warnings: [
      "Illustrative mock values are fabricated for interface demonstration and were not computed from the displayed FASTA.",
      "NODE_demo_2 ends close to cassette_002; the cassette may be incomplete.",
      "CRISPR_002 is a Possible-category array and should be reviewed manually.",
    ],
    provenance: {
      casandra_bundle_id: "casandra-publication-frozen-example",
      casandra_bundle_role: "illustrative_mock",
      casandra_manifest_sha256: "a4f4d3a0010bde7195ea369b6858cfa8daed7a7b68be34af195f5079680fd77f",
      casandra_schema_version: 5,
      crispridentify_version: "2.0.0",
      crispridentify_version_attestation: "illustrative_mock",
      array_overlay_role: "independent_coordinate_overlay",
      array_detection: { requested: true, status: "completed" },
      gene_calling: {
        caller: "Pyrodigal",
        caller_versions: ["3.7.1"],
        requested_mode: "single",
        selected_modes: ["single"],
        requested_translation_table: 11,
        requested_translation_table_scope: "single_mode_training",
        translation_policy: "caller_selected_per_gene",
        translation_table_counts: { 11: 9 },
      },
    },
  },
  interactive_results: {
    schema_version: "1.0.0",
    analysis_mode: "complete_genome",
    coordinates: "1-based-end-inclusive-source-forward",
    sources: [
      { id: "NC_demo_001", length: 3200, molecule: "dna" },
      { id: "NODE_demo_2", length: 1800, molecule: "dna" },
    ],
    features: [
      illustrativeGene({ protein_id: "cas3_demo", contig_id: "NC_demo_001", start: 652, end: 1119, strand: "+", type: "I", subtype: "I-E", profile: "Cas3", score_margin: 8.42, cassette_id: "cassette_001" }, 156),
      illustrativeGene({ protein_id: "cse1_demo", contig_id: "NC_demo_001", start: 1180, end: 1440, strand: "+", type: "I", subtype: "I-E", profile: "Cse1", score_margin: 5.91, cassette_id: "cassette_001" }, 87),
      illustrativeGene({ protein_id: "cse2_demo", contig_id: "NC_demo_001", start: 1482, end: 1694, strand: "+", type: "I", subtype: "I-E", profile: "Cse2", score_margin: 4.73, cassette_id: "cassette_001" }, 71),
      illustrativeGene({ protein_id: "cas7_demo", contig_id: "NC_demo_001", start: 1741, end: 2040, strand: "+", type: "I", subtype: "I-E", profile: "Cas7", score_margin: 7.14, cassette_id: "cassette_001" }, 100),
      illustrativeGene({ protein_id: "cas5_demo", contig_id: "NC_demo_001", start: 2082, end: 2310, strand: "+", type: "I", subtype: "I-E", profile: "Cas5", score_margin: 3.82, cassette_id: "cassette_001" }, 76),
      illustrativeGene({ protein_id: "cas12a_demo", contig_id: "NODE_demo_2", start: 438, end: 1010, strand: "-", type: "V", subtype: "V-A", profile: "Cas12a", score_margin: 9.18, cassette_id: "cassette_002", partial_5prime: true }, 191),
      illustrativeGene({ protein_id: "cas4_demo", contig_id: "NODE_demo_2", start: 1055, end: 1272, strand: "-", type: "V", subtype: "V-A", profile: "Cas4", score_margin: 3.35, cassette_id: "cassette_002" }, 72),
      illustrativeArray({ array_id: "CRISPR_001", contig_id: "NC_demo_001", start: 2480, end: 2898, strand: "+", category: "Bona-fide", repeat_count: 7, model_score: 0.97 }, "GTTCACTGCCGTACAGGCAGCTTAGAAA", ["ACCGTACAGATGGCTAACGTTACCTGAA", "TTAGCGGATACCTGCAATGACGTTACCA", "GGCAATTCGATGCTAACCTGATCGTACA"]),
      illustrativeArray({ array_id: "CRISPR_002", contig_id: "NC_demo_001", start: 210, end: 475, strand: "?", category: "Possible", repeat_count: 4, model_score: 0.64 }, "GTTCACTGCCGTACAGGCAGCTTAGAAA", ["TGCATACCGGATTCAGCTAGGCAATGTC", "CAGTTCGATGGCATACCTGAATCGGTCA"]),
      illustrativeArray({ array_id: "CRISPR_003", contig_id: "NODE_demo_2", start: 1350, end: 1662, strand: "-", category: "Bona-fide", repeat_count: 5, model_score: 0.91 }, "GTCTTGAAACGACGATGACGTTGTAGAA", ["AGGTCAATGCTACCGATTCGGTACATGA", "TTCGACCTGATGGCATACGTCAAGGTAC"]),
      { kind: "cassette", feature_id: "cassette_001", cassette_id: "cassette_001", contig_id: "NC_demo_001", start: 620, end: 2335, class: "1", type: "I", subtype: "I-E", result: "I-E", cas_protein_ids: ["cas3_demo", "cse1_demo", "cse2_demo", "cas7_demo", "cas5_demo"], sequences: [] },
      { kind: "cassette", feature_id: "cassette_002", cassette_id: "cassette_002", contig_id: "NODE_demo_2", start: 410, end: 1290, class: "2", type: "V", subtype: "V-A", result: "V-A", cas_protein_ids: ["cas12a_demo", "cas4_demo"], sequences: [] },
    ],
  },
  artifacts: [],
});

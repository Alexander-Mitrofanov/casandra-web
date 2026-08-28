export const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

export const ANALYSIS_MODES = Object.freeze([
  {
    id: "complete_genome",
    title: "Complete genome",
    label: "Global analysis",
    detail: "will detect, annotate and classify the Cas genes",
    fit: "Complete chromosomes, plasmids, and long assembled contigs",
    sequenceType: "nucleotide",
    helpLabel: "About CasAndra",
    help: "CasAndra detects Cas genes, annotates their likely identity, and classifies CRISPR–Cas systems from protein-sequence and genomic-context evidence.",
  },
  {
    id: "annotate_cas_genes",
    title: "Annotate Cas genes",
    label: "Protein analysis",
    detail: "Analyze every provided protein separately and report its Cas family/profile identity (for example Cas3 or Cas9), or “no cas” from the model result.",
    fit: "Protein FASTA · one record per predicted protein",
    sequenceType: "protein",
  },
  {
    id: "classify_cassette",
    title: "Classify cassette",
    label: "Cassette analysis",
    detail: "Classify a provided set of putative Cas protein sequences, in FASTA order, as a CRISPR type.",
    fit: "One ordered protein FASTA set representing one putative Cas cassette",
    sequenceType: "protein",
  },
  {
    id: "metagenomic",
    title: "Metagenomic analysis",
    label: "Sequence analysis",
    detail: "Detect all Cas genes in every provided nucleotide sequence separately.",
    fit: "Metagenomes, MAG fragments, and short or partial contigs",
    sequenceType: "nucleotide",
  },
]);

export const GENE_MODES = ANALYSIS_MODES;

export function analysisModeDefinition(id) {
  return ANALYSIS_MODES.find((mode) => mode.id === id) || ANALYSIS_MODES[0];
}

export function isProteinAnalysis(id) {
  return analysisModeDefinition(id).sequenceType === "protein";
}

export const PHASES = Object.freeze([
  { id: "queued", label: "Queued", detail: "Waiting for analysis to begin" },
  { id: "casandra", label: "Find Cas genes", detail: "CasAndra predicts proteins and resolves cassettes" },
  { id: "crispridentify", label: "Find CRISPR arrays", detail: "CRISPRidentify v2 adds genomic context" },
  { id: "indexing", label: "Index coordinates", detail: "Source-forward features are prepared for exploration" },
  { id: "packaging", label: "Package outputs", detail: "Checksummed scientific artifacts are finalized" },
  { id: "completed", label: "Ready", detail: "Results are ready to explore" },
]);

export function phasesForAnalysis(analysisMode, includeCrisprArrays = false) {
  const mode = analysisModeDefinition(analysisMode).id;
  const casandra = {
    annotate_cas_genes: { id: "casandra", label: "Annotate proteins", detail: "CasAndra classifies every submitted protein independently" },
    classify_cassette: { id: "casandra", label: "Classify cassette", detail: "CasAndra resolves the CRISPR type represented by the protein set" },
    metagenomic: { id: "casandra", label: "Find Cas genes", detail: "CasAndra detects Cas genes independently in every sequence" },
    complete_genome: PHASES[1],
  }[mode];
  const indexing = ["annotate_cas_genes", "classify_cassette"].includes(mode)
    ? { id: "indexing", label: "Prepare results", detail: "Model calls and evidence are validated for the result summary" }
    : PHASES[3];
  return [
    PHASES[0],
    casandra,
    ...(mode === "complete_genome" && includeCrisprArrays ? [PHASES[2]] : []),
    indexing,
    PHASES[4],
    PHASES[5],
  ];
}

export function phaseIndex(phase) {
  return PHASES.findIndex((item) => item.id === phase);
}

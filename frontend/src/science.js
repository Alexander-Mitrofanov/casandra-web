export const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

export const ANALYSIS_MODES = Object.freeze([
  {
    id: "complete_genome",
    title: "Complete genome",
    label: "Global analysis",
    detail: "will detect, annotate and classify the Cas genes",
    fit: "Complete chromosomes, plasmids, and long assembled contigs",
    sequenceType: "nucleotide",
    helpLabel: "About Complete genome analysis",
    helpIntro: "Complete genome follows the genomic-context pipeline:",
    helpSteps: [
      "Validate every nucleotide FASTA record.",
      "Call and translate coding sequences with Pyrodigal in single-genome mode.",
      "Scan every predicted protein with CasAndra and assign accepted calls a curated Cas-family label plus class, type, and subtype evidence.",
      "Group nearby Cas-positive genes into cassette candidates, classify their architecture, and apply the genome-context evidence gate.",
      "Validate source-forward coordinates and prepare the interactive maps, exact tables, and downloadable artifacts.",
    ],
    helpNote: "When CRISPR array detection is selected, CRISPRidentify runs separately and overlays validated Bona-fide and Possible arrays. Array proximity never confirms, rejects, or changes a CasAndra call.",
  },
  {
    id: "annotate_cas_genes",
    title: "Annotate Cas genes",
    label: "Protein analysis",
    detail: "Analyze every provided protein separately and report its Cas family/profile identity (for example Cas3 or Cas9), or “no cas” from the model result.",
    fit: "Protein FASTA · one record per predicted protein",
    sequenceType: "protein",
    helpLabel: "About Annotate Cas genes analysis",
    helpIntro: "Annotate Cas genes evaluates every supplied protein independently:",
    helpSteps: [
      "Validate the amino-acid FASTA and preserve every record in submitted order.",
      "Scan each protein against CasAndra’s fixed positive and hard-negative profile models.",
      "Apply the frozen decision rule while requiring positive-profile evidence.",
      "Report exactly one result per protein: its curated Cas-family/profile identity or the exact result “no cas”.",
      "Validate the evidence and package every submitted sequence and result for interactive review and download.",
    ],
    helpNote: "This mode does not call genes from DNA and does not infer genomic coordinates, cassettes, or CRISPR arrays. Class, type, and subtype are supplementary protein annotations.",
  },
  {
    id: "classify_cassette",
    title: "Classify cassette",
    label: "Cassette analysis",
    detail: "Classify a provided set of putative Cas protein sequences, in FASTA order, as a CRISPR type.",
    fit: "One ordered protein FASTA set representing one putative Cas cassette",
    sequenceType: "protein",
    helpLabel: "About Classify cassette analysis",
    helpIntro: "Classify cassette interprets one ordered protein set:",
    helpSteps: [
      "Validate the amino-acid FASTA as one proposed cassette and preserve its record order.",
      "Analyze every protein independently as a Cas-family call or “no cas”.",
      "Identify which submitted proteins provide accepted Cas evidence.",
      "Combine the Cas-positive evidence into one class, type, and subtype result; Type III candidates also use ordered protein architecture.",
      "Return the cassette classification together with every per-protein call, sequence, and evidence artifact.",
    ],
    helpNote: "The result is coordinate-free: genomic positions and CRISPR-array evidence are never invented. Insufficient evidence can leave the classification unresolved.",
  },
  {
    id: "metagenomic",
    title: "Metagenomic analysis",
    label: "Sequence analysis",
    detail: "Detect all Cas genes in every provided nucleotide sequence separately.",
    fit: "Metagenomes, MAG fragments, and short or partial contigs",
    sequenceType: "nucleotide",
    helpLabel: "About Metagenomic analysis",
    helpIntro: "Metagenomic analysis keeps every nucleotide record independent:",
    helpSteps: [
      "Validate all nucleotide FASTA records.",
      "Call coding sequences separately in every record with Pyrodigal’s metagenomic mode.",
      "Translate the predicted coding sequences and scan each protein with CasAndra.",
      "Annotate Cas-positive genes, then construct, classify, and evidence-filter cassette candidates only within their source record.",
      "Validate per-sequence coordinates and counts before preparing interactive maps, exact tables, and downloads.",
    ],
    helpNote: "No cassette relationship is inferred across submitted sequences, and this mode does not run CRISPR-array detection.",
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

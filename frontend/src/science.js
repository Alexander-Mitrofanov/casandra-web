export const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

export const GENE_MODES = Object.freeze([
  {
    id: "auto",
    title: "Complete genomes",
    label: "Auto",
    detail: "Use standard Prodigal gene calling for complete or long genomic contigs.",
    fit: "Finished genomes, chromosomes, plasmids, and long assemblies",
  },
  {
    id: "meta",
    title: "Short or fragmented contigs",
    label: "Meta",
    detail: "Use metagenomic gene calling to retain partial coding sequences near contig edges.",
    fit: "Metagenomes, MAG fragments, and short contigs",
  },
]);

export const PHASES = Object.freeze([
  { id: "queued", label: "Queued", detail: "Waiting for analysis to begin" },
  { id: "casandra", label: "Find Cas genes", detail: "CasAndra predicts proteins and resolves cassettes" },
  { id: "crispridentify", label: "Find CRISPR arrays", detail: "CRISPRidentify v2 adds genomic context" },
  { id: "indexing", label: "Index coordinates", detail: "Source-forward features are prepared for exploration" },
  { id: "packaging", label: "Package outputs", detail: "Checksummed scientific artifacts are finalized" },
  { id: "completed", label: "Ready", detail: "Results are ready to explore" },
]);

export function phaseIndex(phase) {
  return PHASES.findIndex((item) => item.id === phase);
}

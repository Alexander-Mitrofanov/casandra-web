import { normalizeFastaInput } from "./fasta.js";

export function buildSubmission({ sequence, filename, analysisMode, geneMode, includeCrisprArrays = false }) {
  analysisMode ||= geneMode === "meta" ? "metagenomic" : "complete_genome";
  const supportedModes = new Set(["complete_genome", "annotate_cas_genes", "classify_cassette", "metagenomic"]);
  const normalizedMode = supportedModes.has(analysisMode) ? analysisMode : "complete_genome";
  const payload = {
    sequence: normalizeFastaInput(sequence),
    analysis_mode: normalizedMode,
    include_crispr_arrays: normalizedMode === "complete_genome" && Boolean(includeCrisprArrays),
  };
  const cleanName = String(filename || "").trim();
  if (cleanName) payload.filename = cleanName;
  return payload;
}

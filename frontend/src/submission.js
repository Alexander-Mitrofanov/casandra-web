import { normalizeFastaInput } from "./fasta.js";

export function buildSubmission({ sequence, filename, geneMode }) {
  const payload = {
    sequence: normalizeFastaInput(sequence),
    gene_mode: geneMode === "meta" ? "meta" : "auto",
  };
  const cleanName = String(filename || "").trim();
  if (cleanName) payload.filename = cleanName;
  return payload;
}

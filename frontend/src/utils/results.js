import { asArray } from "./formatting.js";

export function summaryFromJob(job) {
  return job?.summary && typeof job.summary === "object" ? job.summary : null;
}

export function featuresForContig(summary, contigId) {
  const matches = (rows) => asArray(rows).filter((row) => row?.contig_id === contigId);
  return {
    cassettes: matches(summary?.cassettes),
    casProteins: matches(summary?.cas_proteins),
    crisprArrays: matches(summary?.crispr_arrays),
  };
}

export function sourceForwardInterval(feature, contigLength) {
  const length = Math.max(1, Number(contigLength) || 1);
  const rawStart = Number(feature?.start);
  const rawEnd = Number(feature?.end);
  const start = Math.min(length, Math.max(1, Math.min(rawStart, rawEnd) || 1));
  const end = Math.min(length, Math.max(start, Math.max(rawStart, rawEnd) || start));
  return { start, end, length: end - start + 1 };
}

export function contigsWithFeatures(summary) {
  const supplied = asArray(summary?.contigs).filter((contig) => contig?.id);
  if (supplied.length) return supplied;
  const lengths = new Map();
  for (const row of [
    ...asArray(summary?.cassettes),
    ...asArray(summary?.cas_proteins),
    ...asArray(summary?.crispr_arrays),
  ]) {
    if (!row?.contig_id) continue;
    lengths.set(row.contig_id, Math.max(lengths.get(row.contig_id) || 1, Number(row.end) || 1));
  }
  return [...lengths].map(([id, length]) => ({ id, length }));
}

import { describe, expect, it } from "vitest";

import { inspectFasta, normalizeFastaInput, readableBases } from "../src/fasta.js";
import { buildSubmission } from "../src/submission.js";

describe("nucleotide FASTA inspection", () => {
  it("accepts multiple nucleotide records and normalizes ASCII case", () => {
    const result = inspectFasta(">ctg_1 note\nacgtnryk\n>ctg_2\nGGCC\n");
    expect(result.valid).toBe(true);
    expect(result.recordCount).toBe(2);
    expect(result.baseCount).toBe(12);
    expect(result.records[0].sequence).toBe("ACGTNRYK");
  });

  it("wraps a bare nucleotide sequence as one web input record", () => {
    const result = inspectFasta("ACGTACGT");
    expect(result.valid).toBe(true);
    expect(result.records[0].identifier).toBe("sequence_1");
  });

  it("rejects protein symbols and duplicate identifiers", () => {
    const result = inspectFasta(">same\nACGTZ\n>same\nACGT\n");
    expect(result.valid).toBe(false);
    expect(result.errors.join(" ")).toMatch(/unsupported nucleotide symbol Z/i);
    expect(result.errors.join(" ")).toMatch(/duplicated/i);
  });

  it("matches the backend record-ID contract without lossy normalization", () => {
    expect(inspectFasta(">a:b\nACGT\n>a_b\nACGT\n").valid).toBe(true);
    const invalid = inspectFasta(">bad/id\nACGT\n");
    expect(invalid.valid).toBe(false);
    expect(invalid.errors.join(" ")).toMatch(/record IDs/i);
  });

  it("accepts a tab in a FASTA header description", () => {
    expect(inspectFasta(">ctg\tdescription\nACGT\n").valid).toBe(true);
  });

  it("removes a UTF-8 BOM for both inspection and submission", () => {
    const sequence = "\ufeff>ctg\nACGT\n";
    expect(inspectFasta(sequence).valid).toBe(true);
    expect(normalizeFastaInput(sequence)).toBe(">ctg\nACGT\n");
    expect(buildSubmission({ sequence, filename: "a.fa", geneMode: "auto" }).sequence).toBe(
      ">ctg\nACGT\n",
    );
  });

  it("enforces the configured header boundary", () => {
    expect(inspectFasta(">too-long\nACGT", { maxHeaderCharacters: 4 }).errors[0]).toMatch(/exceeds 4/);
  });

  it("formats genomic sizes", () => {
    expect(readableBases(42)).toBe("42 bp");
    expect(readableBases(2500)).toBe("2.5 kbp");
    expect(readableBases(2_500_000)).toBe("2.50 Mbp");
  });
});

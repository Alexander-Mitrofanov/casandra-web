import { describe, expect, it } from "vitest";

import { SAMPLE_JOB } from "../src/sample.js";
import { contigsWithFeatures, featuresForContig, sourceForwardInterval } from "../src/utils/results.js";

describe("result coordinate helpers", () => {
  it("groups cassette, Cas protein, and array features by contig", () => {
    const features = featuresForContig(SAMPLE_JOB.summary, "NC_demo_001");
    expect(features.cassettes).toHaveLength(1);
    expect(features.casProteins).toHaveLength(5);
    expect(features.crisprArrays).toHaveLength(2);
  });

  it("preserves source-forward coordinates for minus-strand genes", () => {
    const minus = SAMPLE_JOB.summary.cas_proteins.find((row) => row.strand === "-");
    expect(sourceForwardInterval(minus, 1800)).toEqual({ start: 438, end: 1010, length: 573 });
  });

  it("can derive contigs when an older summary omits the contig index", () => {
    const contigs = contigsWithFeatures({ cas_proteins: [{ contig_id: "ctg", start: 8, end: 212 }] });
    expect(contigs).toEqual([{ id: "ctg", length: 212 }]);
  });
});

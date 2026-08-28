import { describe, expect, it } from "vitest";

import { contigsWithFeatures, featuresForContig, sourceForwardInterval } from "../src/utils/results.js";
import { exampleJob } from "./exampleFixtures.js";

const completeExample = exampleJob("complete_genome");
const metagenomicExample = exampleJob("metagenomic");

describe("result coordinate helpers", () => {
  it("groups Cas protein and array features by source contig", () => {
    const features = featuresForContig(completeExample.summary, "spyogenes_type_IIA_complete");
    expect(features.cassettes).toHaveLength(0);
    expect(features.casProteins).toHaveLength(5);
    expect(features.crisprArrays).toHaveLength(2);
  });

  it("preserves source-forward coordinates for minus-strand genes", () => {
    const minus = metagenomicExample.summary.cas_proteins.find((row) => row.strand === "-");
    const contig = metagenomicExample.summary.contigs.find((row) => row.id === minus.contig_id);
    expect(sourceForwardInterval(minus, contig.length)).toEqual({ start: minus.start, end: minus.end, length: minus.end - minus.start + 1 });
  });

  it("can derive contigs when an older summary omits the contig index", () => {
    const contigs = contigsWithFeatures({ cas_proteins: [{ contig_id: "ctg", start: 8, end: 212 }] });
    expect(contigs).toEqual([{ id: "ctg", length: 212 }]);
  });
});

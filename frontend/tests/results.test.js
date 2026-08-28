import { describe, expect, it } from "vitest";

import { contigsWithFeatures, featuresForContig, sourceForwardInterval } from "../src/utils/results.js";
import { exampleJob } from "./exampleFixtures.js";

const completeExample = exampleJob("complete_genome");
const metagenomicExample = exampleJob("metagenomic");

describe("result coordinate helpers", () => {
  it("groups arrays-off complete-genome features by source contig", () => {
    const sourceId = completeExample.summary.contigs[0].id;
    const features = featuresForContig(completeExample.summary, sourceId);
    expect(features.casProteins.length).toBeGreaterThan(0);
    expect(features.crisprArrays).toEqual([]);
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

import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { exampleJob, exampleText } from "./exampleFixtures.js";

const root = resolve(process.cwd(), "public/examples");
const modes = ["complete_genome", "annotate_cas_genes", "classify_cassette", "metagenomic"];

describe("captured four-mode examples", () => {
  it.each(modes)("keeps the %s input, summary, interactive result, and artifacts consistent", (mode) => {
    const job = exampleJob(mode);
    expect(job.status).toBe("completed");
    expect(job.options.analysis_mode).toBe(mode);
    expect(job.summary.analysis_mode).toBe(mode);
    expect(job.interactive_results.analysis_mode).toBe(mode);
    expect(job.input.source_ids).toEqual(job.interactive_results.sources.map((source) => source.id));

    const detailsArtifact = job.artifacts.find((artifact) => artifact.name === "casandra-results.json");
    const csvArtifact = job.artifacts.find((artifact) => artifact.name === "casandra-results.csv");
    expect(detailsArtifact).toBeTruthy();
    expect(csvArtifact).toBeTruthy();
    expect(job.artifacts.some((artifact) => artifact.format === "fasta")).toBe(true);
    expect(JSON.parse(exampleText(mode, "artifacts/casandra-results.json"))).toEqual(job.interactive_results);
    expect(exampleText(mode, "artifacts/casandra-results.csv").trim().split("\n")).toHaveLength(job.interactive_results.features.length + 1);

    for (const artifact of job.artifacts) {
      const path = resolve(root, mode, "artifacts", artifact.name);
      expect(existsSync(path)).toBe(true);
      const content = readFileSync(path);
      expect(content).toHaveLength(artifact.size_bytes);
      expect(createHash("sha256").update(content).digest("hex")).toBe(artifact.sha256);
    }
  });

  it("contains mode-specific graphical content", () => {
    expect(exampleJob("complete_genome").summary.crispr_arrays.length).toBeGreaterThan(0);
    expect(exampleJob("annotate_cas_genes").summary.protein_predictions).toHaveLength(5);
    expect(exampleJob("classify_cassette").summary.cassette_classification.result).toBeTruthy();
    expect(exampleJob("metagenomic").summary.sequence_results).toHaveLength(2);
  });
});

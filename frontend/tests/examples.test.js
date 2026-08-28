import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";

import { loadExampleJob } from "../src/examples.js";
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
    expect(job.options.include_crispr_arrays).toBe(false);
    expect(job.summary.include_crispr_arrays).toBe(false);
    expect(job.interactive_results.summary.include_crispr_arrays).toBe(false);
    expect(job.summary.provenance.array_detection).toEqual({ requested: false, status: "not_requested" });
    expect(job.summary.crispr_arrays).toEqual([]);
    expect(job.interactive_results.features.some((row) => row.kind === "crispr_array")).toBe(false);
    expect(job.artifacts.some((artifact) => /crispr/i.test(`${artifact.name} ${artifact.scope || ""} ${artifact.role || ""}`))).toBe(false);
    expect(job.input.source_ids).toEqual(job.interactive_results.sources.map((source) => source.id));

    const detailsArtifact = job.artifacts.find((artifact) => artifact.name === "casandra-results.json");
    const csvArtifact = job.artifacts.find((artifact) => artifact.name === "casandra-results.csv");
    expect(detailsArtifact).toBeTruthy();
    expect(csvArtifact).toBeTruthy();
    expect(job.artifacts.some((artifact) => artifact.format === "fasta")).toBe(true);
    expect(JSON.parse(exampleText(mode, "artifacts/casandra-results.json"))).toEqual(job.interactive_results);
    expect(JSON.parse(exampleText(mode, "artifacts/result-summary.json"))).toEqual(job.summary);
    expect(exampleText(mode, "artifacts/casandra-results.csv").trim().split("\n")).toHaveLength(job.interactive_results.features.length + 1);

    const listedNames = job.artifacts.map((artifact) => artifact.name).sort();
    const capturedNames = readdirSync(resolve(root, mode, "artifacts"), { withFileTypes: true })
      .filter((entry) => entry.isFile())
      .map((entry) => entry.name)
      .sort();
    expect(capturedNames).toEqual(listedNames);

    for (const artifact of job.artifacts) {
      const path = resolve(root, mode, "artifacts", artifact.name);
      expect(artifact.bundled_path).toBe(`examples/${mode}/artifacts/${artifact.name}`);
      expect(existsSync(path)).toBe(true);
      const content = readFileSync(path);
      expect(content).toHaveLength(artifact.size_bytes);
      expect(createHash("sha256").update(content).digest("hex")).toBe(artifact.sha256);
    }
  });

  it("contains mode-specific graphical content", () => {
    expect(exampleJob("complete_genome").summary.cas_proteins.length).toBeGreaterThan(0);
    expect(exampleJob("complete_genome").summary.crispr_arrays).toEqual([]);
    expect(exampleJob("annotate_cas_genes").summary.protein_predictions).toHaveLength(5);
    expect(exampleJob("classify_cassette").summary.cassette_classification.result).toBeTruthy();
    expect(exampleJob("metagenomic").summary.sequence_results).toHaveLength(2);
  });

  it("uses a full genome and exposes the genuine Type II-A cassette consistently", () => {
    const job = exampleJob("complete_genome");
    const sourceManifest = JSON.parse(readFileSync(resolve(root, "source-manifest.json"), "utf-8"));
    const sequenceLength = exampleText("complete_genome", "input.fna")
      .split(/\r?\n/)
      .filter((line) => line && !line.startsWith(">"))
      .join("").length;
    expect(sequenceLength).toBe(1_852_433);
    expect(sourceManifest).toMatchObject({
      reference: "NC_002737.2",
      complete_genome_length: sequenceLength,
      complete_genome_sequence_sha256: "babc1e875c480f5db9cd79cb9783bd1c6ce56d83fad41cbc31fd27054254eb9b",
    });
    expect(job.input.total_sequence_length).toBe(sequenceLength);
    expect(job.input.source_ids).toEqual(["NC_002737.2_complete_genome"]);

    const cassette = job.summary.cassettes.find((row) => row.type === "II" && row.subtype === "II-A");
    expect(cassette).toMatchObject({
      start: 854_751,
      end: 860_064,
      cas_gene_count: 3,
      method: "type_ii_ordered_profile_architecture_extratrees",
      evidence_gate: { accepted: true, rule: "class2_multi_gene" },
    });
    const cassetteGenes = job.summary.cas_proteins
      .filter((row) => row.cassette_id === cassette.cassette_id)
      .map((row) => row.result);
    expect(cassetteGenes).toEqual(["Cas9", "Cas1", "Cas2"]);
    expect(exampleText("complete_genome", "artifacts/cassettes.tsv")).toContain("\tII\tII-A\ttype_ii_ordered_profile_architecture_extratrees\t");
    expect(exampleText("complete_genome", "artifacts/casandra.gff3")).toContain("cas_type=II;cas_subtype=II-A;method=type_ii_ordered_profile_architecture_extratrees");
    expect(exampleJob("classify_cassette").summary.cassette_classification.result).toBe("II-A");
    expect(exampleJob("metagenomic").summary.cassettes).toEqual(expect.arrayContaining([
      expect.objectContaining({ contig_id: "spyogenes_type_IIA_locus", type: "II", subtype: "II-A" }),
    ]));
  });
});

function arraysOffCompleteJob() {
  const summary = {
    schema_version: "1.1.0",
    analysis_mode: "complete_genome",
    include_crispr_arrays: false,
    overview: { crispr_array_count: 0 },
    cassettes: [],
    cas_proteins: [],
    crispr_arrays: [],
    detail_truncated: { crispr_arrays: false },
    provenance: {
      array_detection: { requested: false, status: "not_requested" },
      array_overlay_role: "not_requested",
      crispridentify_version: null,
      crispridentify_version_attestation: null,
    },
  };
  return {
    status: "completed",
    options: { analysis_mode: "complete_genome", include_crispr_arrays: false },
    input: { filename: "input.fna" },
    summary,
    interactive_results: {
      analysis_mode: "complete_genome",
      sources: [{ id: "complete", length: 4 }],
      features: [],
      feature_counts: {},
      summary: structuredClone(summary),
    },
    artifacts: [],
  };
}

async function loadSyntheticExample(job) {
  vi.stubGlobal("fetch", vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => job,
  })));
  return loadExampleJob("complete_genome");
}

describe("precomputed array-option validation", () => {
  it("accepts an internally consistent arrays-off complete-genome snapshot", async () => {
    const job = arraysOffCompleteJob();
    await expect(loadSyntheticExample(job)).resolves.toBe(job);
  });

  it.each([
    ["summary array rows", (job) => job.summary.crispr_arrays.push({ array_id: "array-1" })],
    ["interactive array features", (job) => job.interactive_results.features.push({ kind: "crispr_array", feature_id: "array-1" })],
    ["CRISPR artifacts", (job) => job.artifacts.push({ name: "crispr-arrays.fna", role: "sequences", scope: "crispr_arrays" })],
    ["requested-array provenance", (job) => { job.summary.provenance.array_detection = { requested: true, status: "completed" }; }],
    ["interactive-summary provenance", (job) => { job.interactive_results.summary.provenance.array_overlay_role = "independent_coordinate_overlay"; }],
  ])("rejects arrays-off fixtures containing %s", async (_label, mutate) => {
    const job = arraysOffCompleteJob();
    mutate(job);
    await expect(loadSyntheticExample(job)).rejects.toThrow("inconsistent with its analysis mode");
  });
});

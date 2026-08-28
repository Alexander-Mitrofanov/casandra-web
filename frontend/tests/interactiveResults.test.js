import { fireEvent, render, screen, waitFor, within } from "@testing-library/vue";
import { describe, expect, it, vi } from "vitest";

import { api } from "../src/api.js";
import DownloadsPanel from "../src/components/results/DownloadsPanel.vue";
import FeatureInspector from "../src/components/results/FeatureInspector.vue";
import ProteinExplorer from "../src/components/results/ProteinExplorer.vue";
import ResultsView from "../src/components/results/ResultsView.vue";
import { exampleFetch, exampleJob } from "./exampleFixtures.js";

const credential = {
  jobId: "0123456789abcdef0123456789abcdef",
  accessToken: "abcdefghijklmnopqrstuvwxyzABCDEFGH123456789_-",
};

function sequence(key, value = "MSTNPKPQR") {
  return {
    key,
    label: "Submitted protein",
    molecule: "protein",
    orientation: "submitted_fasta_order",
    length: value.length,
    sha256: "a".repeat(64),
    sequence: value,
  };
}

function fastaRecords(value) {
  const records = [];
  let current = null;
  for (const line of String(value || "").trim().split(/\r?\n/)) {
    if (line.startsWith(">")) {
      current = { header: line.slice(1), sequence: "" };
      records.push(current);
    } else if (current) {
      current.sequence += line.trim();
    }
  }
  return records;
}

describe("interactive scientific results", () => {
  it("opens captured genomic features with their exact sequence contents by keyboard", async () => {
    const completed = exampleJob("complete_genome");
    render(ResultsView, { props: { job: completed } });
    expect(screen.getByText("Completed analysis")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/precomput|illustrative|fabricat|not computed/i);
    const resultNav = screen.getByRole("navigation", { name: "Result sections" });
    for (const [name, target] of [[/Overview/i, "result-overview"], [/Explore results/i, "result-explorer"], [/Download files/i, "result-downloads"], [/Exact data/i, "result-tables"]]) {
      expect(within(resultNav).getByRole("link", { name })).toHaveAttribute("href", `#${target}`);
      expect(document.getElementById(target)).toBeInTheDocument();
    }

    expect(screen.getByRole("button", { pressed: true, name: /Cas gene/i })).toBeInTheDocument();
    const gene = screen.getByRole("button", { name: /Cas gene Cas9/i });
    await fireEvent.keyDown(gene, { key: "Enter" });
    expect(screen.getByRole("heading", { name: /casandra\|.*cds=000012/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Translated Cas protein sequence")).toHaveTextContent(/^M/);

    const array = screen.getByRole("button", { name: /CRISPR-15819-16184-bf1, CRISPR array/i });
    await fireEvent.keyDown(array, { key: " " });
    expect(screen.getByRole("heading", { name: "CRISPR-15819-16184-bf1" })).toBeInTheDocument();
    const arrayFeature = completed.interactive_results.features.find((feature) => feature.feature_id === "CRISPR-15819-16184-bf1");
    expect(screen.getByLabelText("Consensus repeat sequence")).toBeVisible();
    expect(screen.getByLabelText("Consensus repeat sequence")).toHaveTextContent(arrayFeature.consensus_repeat);
    const spacerList = screen.getByRole("list", { name: "Ordered spacer sequences" });
    expect(within(spacerList).getAllByRole("listitem")).toHaveLength(arrayFeature.spacer_count);
    for (const [index, spacer] of arrayFeature.spacers.entries()) {
      const sequence = screen.getByLabelText(`Spacer ${index + 1} sequence`);
      expect(sequence).toBeVisible();
      expect(sequence).toHaveTextContent(spacer);
    }
    const composition = screen.getByRole("list", { name: "Ordered CRISPR repeat and spacer composition" });
    expect(within(composition).getAllByRole("listitem").map((item) => item.getAttribute("aria-label"))).toEqual([
      "Repeat 1, represented by the reported consensus repeat", "Spacer 1",
      "Repeat 2, represented by the reported consensus repeat", "Spacer 2",
      "Repeat 3, represented by the reported consensus repeat", "Spacer 3",
      "Repeat 4, represented by the reported consensus repeat", "Spacer 4",
      "Repeat 5, represented by the reported consensus repeat", "Spacer 5",
      "Repeat 6, represented by the reported consensus repeat",
    ]);
    expect(screen.getByLabelText("Array interval on submitted source sequence")).toBeVisible();
    const previousClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");
    const writeText = vi.fn().mockResolvedValue(undefined);
    let copiedFasta = "";
    try {
      Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
      await fireEvent.click(screen.getByRole("button", { name: /Copy all sequences in CRISPR-15819-16184-bf1/i }));
      copiedFasta = writeText.mock.calls.at(-1)[0];
    } finally {
      if (previousClipboard) Object.defineProperty(navigator, "clipboard", previousClipboard);
      else delete navigator.clipboard;
    }
    const copiedRecords = fastaRecords(copiedFasta);
    const expectedSequences = [
      arrayFeature.sequences.find((item) => item.key === "array_source_forward"),
      arrayFeature.sequences.find((item) => item.key === "consensus_repeat"),
      ...arrayFeature.sequences.filter((item) => /^spacer_\d+$/.test(item.key)).sort((left, right) => Number(left.key.split("_").at(-1)) - Number(right.key.split("_").at(-1))),
    ];
    expect(copiedRecords.map((record) => record.header.split(/\s/)[0].split("|").at(-1))).toEqual(expectedSequences.map((item) => item.key));
    expect(copiedRecords.map((record) => record.sequence)).toEqual(expectedSequences.map((item) => item.sequence));

    const saved = [];
    const objectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:array-contents");
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function click() {
      saved.push({ href: this.href, filename: this.download });
    });
    await fireEvent.click(screen.getByRole("button", { name: /Download all sequences in CRISPR-15819-16184-bf1 as FASTA/i }));
    const downloadedBlob = objectUrl.mock.calls.at(-1)[0];
    expect(downloadedBlob).toBeInstanceOf(Blob);
    expect(downloadedBlob.type).toBe("text/x-fasta;charset=utf-8");
    expect(await downloadedBlob.text()).toBe(copiedFasta);
    expect(saved).toEqual([{ href: "blob:array-contents", filename: "CRISPR-15819-16184-bf1-array-contents.fna" }]);

    const secondArray = screen.getByRole("button", { name: /CRISPR-19375-19534-p1, CRISPR array/i });
    await fireEvent.click(secondArray);
    const secondFeature = completed.interactive_results.features.find((feature) => feature.feature_id === "CRISPR-19375-19534-p1");
    expect(screen.getByRole("heading", { name: "CRISPR-19375-19534-p1" })).toBeInTheDocument();
    expect(screen.getByLabelText("Consensus repeat sequence")).toHaveTextContent(secondFeature.consensus_repeat);
    expect(within(screen.getByRole("list", { name: "Ordered spacer sequences" })).getAllByRole("listitem")).toHaveLength(secondFeature.spacer_count);
    expect(within(screen.getByRole("list", { name: "Ordered CRISPR repeat and spacer composition" })).getAllByRole("listitem")).toHaveLength((secondFeature.spacer_count * 2) + 1);
  });

  it.each(["complete_genome", "annotate_cas_genes", "classify_cassette", "metagenomic"])("keeps every result section directly reachable in %s", (mode) => {
    render(ResultsView, { props: { job: exampleJob(mode) } });
    const navigation = screen.getByRole("navigation", { name: "Result sections" });
    expect(within(navigation).getAllByRole("link")).toHaveLength(4);
    for (const [name, target] of [[/Overview/i, "result-overview"], [/Explore results/i, "result-explorer"], [/Download files/i, "result-downloads"], [/Exact data/i, "result-tables"]]) {
      expect(within(navigation).getByRole("link", { name })).toHaveAttribute("href", `#${target}`);
      expect(document.getElementById(target)).toBeInTheDocument();
    }
    const downloads = within(document.getElementById("result-downloads"));
    expect(downloads.getAllByRole("button", { name: /as JSON$/i }).length).toBeGreaterThan(0);
    expect(downloads.getAllByRole("button", { name: /as CSV$/i }).length).toBeGreaterThan(0);
    expect(downloads.getAllByRole("button", { name: /as FASTA$/i }).length).toBeGreaterThan(0);
  });

  it("preserves non-contiguous reported spacer positions without adding per-spacer controls", () => {
    render(FeatureInspector, { props: { feature: {
      kind: "crispr_array",
      feature_id: "array-with-omission",
      repeat_count: 4,
      consensus_repeat: "GTTTA",
      spacers: ["AACCGG", "TTGGCC"],
      spacer_indices: [1, 3],
    } } });

    const spacerList = screen.getByRole("list", { name: "Ordered spacer sequences" });
    expect(within(spacerList).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      expect.stringContaining("Spacer 1"),
      expect.stringContaining("Spacer 3"),
    ]);
    const composition = screen.getByRole("list", { name: "Ordered CRISPR repeat and spacer composition" });
    expect(within(composition).getAllByRole("listitem").map((item) => item.getAttribute("aria-label"))).toEqual([
      "Repeat 1, represented by the reported consensus repeat", "Spacer 1",
      "Repeat 2, represented by the reported consensus repeat",
      "Repeat 3, represented by the reported consensus repeat", "Spacer 3",
      "Repeat 4, represented by the reported consensus repeat",
    ]);
    expect(screen.queryByRole("button", { name: /^Spacer /i })).not.toBeInTheDocument();
  });

  it("keeps Cas and no-cas protein calls graphical, selectable, and sequence-bearing", async () => {
    const summary = {
      analysis_mode: "annotate_cas_genes",
      protein_predictions: [
        { protein_id: "cas3", input_index: 0, is_cas: true, result: "Cas3", type: "I", score_margin: 4.2 },
        { protein_id: "other", input_index: 1, is_cas: false, result: "no cas", score_margin: -1.1 },
      ],
    };
    const details = {
      features: [
        { kind: "protein", feature_id: "cas3", protein_id: "cas3", input_index: 0, is_cas: true, result: "Cas3", type: "I", score_margin: 4.2, sequences: [sequence("protein")] },
        { kind: "protein", feature_id: "other", protein_id: "other", input_index: 1, is_cas: false, result: "no cas", score_margin: -1.1, sequences: [sequence("protein", "VVVVVVVV")] },
      ],
    };
    render(ProteinExplorer, { props: { summary, details } });

    expect(screen.getByRole("img", { name: /Cas and no-cas composition/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "cas3" })).toBeInTheDocument();
    const noCas = screen.getByRole("button", { name: /other: no cas; score margin -1.100/i });
    await fireEvent.click(noCas);
    expect(screen.getByRole("heading", { name: "other" })).toBeInTheDocument();
    expect(screen.getByText(/No Cas profile passed the model decision rule/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Submitted protein sequence")).toHaveTextContent("VVVVVVVV");
  });

  it("shows a coordinate-free, ordered cassette with every submitted protein selectable", async () => {
    const summary = {
      analysis_mode: "classify_cassette",
      protein_predictions: [
        { protein_id: "cas10", input_index: 0, residue_count: 120, is_cas: true, result: "Cas10", type: "III" },
        { protein_id: "other", input_index: 1, residue_count: 40, is_cas: false, result: "no cas" },
        { protein_id: "cas7", input_index: 2, residue_count: 90, is_cas: true, result: "Cas7", type: "III" },
      ],
      cassette_classification: { result: "III-A", type: "III", subtype: "III-A", method: "ordered" },
    };
    const details = {
      features: summary.protein_predictions.map((row) => ({ ...row, kind: "protein", feature_id: row.protein_id, sequences: [sequence("protein")] })),
    };
    render(ProteinExplorer, { props: { summary, details } });

    const lane = screen.getByRole("list", { name: "Ordered submitted proteins" });
    expect(screen.getByRole("heading", { name: "cas10" })).toBeInTheDocument();
    const items = within(lane).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items.map((item) => within(item).getByRole("button").textContent)).toEqual([
      expect.stringContaining("cas10"),
      expect.stringContaining("other"),
      expect.stringContaining("cas7"),
    ]);
    await fireEvent.click(within(items[1]).getByRole("button"));
    expect(screen.getByRole("heading", { name: "other" })).toBeInTheDocument();
    expect(screen.getByText(/coordinate-free protein set/i)).toBeInTheDocument();
  });

  it("loads complete details through the authenticated artifact route", async () => {
    const details = {
      schema_version: "1.0.0",
      analysis_mode: "annotate_cas_genes",
      sources: [{ id: "protein_a", length: 9, molecule: "protein" }],
      features: [{ kind: "protein", feature_id: "protein_a", protein_id: "protein_a", input_index: 0, is_cas: true, result: "Cas3", score_margin: 3.1, sequences: [sequence("protein")] }],
    };
    vi.spyOn(api, "downloadArtifact").mockResolvedValue({
      size: 1_000,
      text: async () => JSON.stringify(details),
    });
    const job = {
      job_id: credential.jobId,
      status: "completed",
      options: { analysis_mode: "annotate_cas_genes" },
      summary: {
        schema_version: "1.1.0",
        analysis_mode: "annotate_cas_genes",
        overview: { protein_count: 1, cas_protein_count: 1 },
        protein_predictions: [{ protein_id: "protein_a", input_index: 0, is_cas: true, result: "Cas3", score_margin: 3.1 }],
        provenance: {},
      },
      artifacts: [{ artifact_id: "detail-artifact", name: "casandra-results.json", role: "results", format: "json", scope: "all_features", size_bytes: 1_000 }],
    };

    render(ResultsView, { props: { job, credential, maxArtifactBytes: 10_000 } });
    await waitFor(() => expect(api.downloadArtifact).toHaveBeenCalledWith(
      credential.jobId,
      "detail-artifact",
      credential.accessToken,
    ));
    await waitFor(() => expect(screen.getByRole("button", { name: /protein_a: Cas3/i })).toBeInTheDocument());
    await fireEvent.click(screen.getByRole("button", { name: /protein_a: Cas3/i }));
    expect(screen.getByLabelText("Submitted protein sequence")).toHaveTextContent("MSTNPKPQR");
  });

  it("lets the user choose FASTA, CSV, or JSON without exposing the access key", async () => {
    const artifacts = [
      { artifact_id: "json", name: "casandra-results.json", role: "results", format: "json", scope: "all_features", size_bytes: 120, sha256: "1".repeat(64) },
      { artifact_id: "csv", name: "casandra-results.csv", role: "results", format: "csv", scope: "all_features", size_bytes: 90, sha256: "2".repeat(64) },
      { artifact_id: "fasta", name: "cas-proteins.faa", role: "sequences", format: "fasta", scope: "cas_proteins", molecule: "protein", size_bytes: 75, sha256: "3".repeat(64) },
      { artifact_id: "zip", name: "casandra-results.zip", role: "bundle", format: "zip", scope: "all_artifacts", size_bytes: 400, sha256: "4".repeat(64) },
    ];
    vi.spyOn(api, "downloadArtifact").mockResolvedValue(new Blob([">cas3\nMSTN\n"], { type: "text/x-fasta" }));
    render(DownloadsPanel, { props: { job: { artifacts }, credential } });

    expect(screen.getByRole("button", { name: "Download Complete results as JSON" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download Complete results as CSV" })).toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: /Detected Cas proteins/i }));
    await waitFor(() => expect(api.downloadArtifact).toHaveBeenCalledWith(
      credential.jobId,
      "fasta",
      credential.accessToken,
    ));
    expect(document.body.textContent).not.toContain(credential.accessToken);
    expect(screen.getByText(/Technical artifacts and complete bundle/i)).toBeInTheDocument();
  });

  it("labels only primary formats that are actually available", () => {
    render(DownloadsPanel, { props: { job: { artifacts: [
      { artifact_id: "csv", name: "casandra-results.csv", role: "results", format: "csv", scope: "all_features", size_bytes: 90 },
    ] }, credential } });
    const note = screen.getByText(/no format switching required/i).closest(".download-format-note");
    expect(within(note).getByText("CSV")).toBeInTheDocument();
    expect(within(note).queryByText("JSON")).not.toBeInTheDocument();
    expect(within(note).queryByText("FASTA")).not.toBeInTheDocument();
  });

  it("downloads the same FASTA, CSV, and JSON controls for a completed built-in run", async () => {
    const downloads = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function click() {
      downloads.push({ href: this.href, filename: this.download, connected: this.isConnected });
    });
    const completed = exampleJob("annotate_cas_genes");
    render(DownloadsPanel, { props: { job: completed } });

    await fireEvent.click(screen.getByRole("button", { name: "Download Complete results as JSON" }));
    await fireEvent.click(screen.getByRole("button", { name: "Download Complete results as CSV" }));
    await fireEvent.click(screen.getByRole("button", { name: "Download All submitted proteins as FASTA" }));
    expect(downloads).toEqual([
      { href: expect.stringMatching(/examples\/annotate_cas_genes\/artifacts\/casandra-results\.json$/), filename: "casandra-results.json", connected: true },
      { href: expect.stringMatching(/examples\/annotate_cas_genes\/artifacts\/casandra-results\.csv$/), filename: "casandra-results.csv", connected: true },
      { href: expect.stringMatching(/examples\/annotate_cas_genes\/artifacts\/all-proteins\.faa$/), filename: "all-proteins.faa", connected: true },
    ]);
  });
});

import { fireEvent, render, screen, waitFor, within } from "@testing-library/vue";
import { describe, expect, it, vi } from "vitest";

import { api } from "../src/api.js";
import DownloadsPanel from "../src/components/results/DownloadsPanel.vue";
import ProteinExplorer from "../src/components/results/ProteinExplorer.vue";
import ResultsView from "../src/components/results/ResultsView.vue";
import { SAMPLE_JOB } from "../src/sample.js";

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

describe("interactive scientific results", () => {
  it("opens every illustrative genomic feature with sequence contents by keyboard", async () => {
    render(ResultsView, { props: { job: SAMPLE_JOB, sample: true } });

    const gene = screen.getByRole("button", { name: /cas3_demo, Cas gene Cas3/i });
    await fireEvent.keyDown(gene, { key: "Enter" });
    expect(screen.getByRole("heading", { name: "cas3_demo" })).toBeInTheDocument();
    expect(screen.getByLabelText("Translated Cas protein sequence")).toHaveTextContent(/^M/);

    const array = screen.getByRole("button", { name: /CRISPR_001, CRISPR array/i });
    await fireEvent.keyDown(array, { key: " " });
    expect(screen.getByRole("heading", { name: "CRISPR_001" })).toBeInTheDocument();
    expect(screen.getByLabelText("Consensus repeat sequence")).toHaveTextContent("GTTCACTGCCGTACAGGCAGCTTAGAAA");
    expect(screen.getByLabelText("Spacer 1 sequence")).toHaveTextContent("ACCGTACAGATGGCTAACGTTACCTGAA");
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

    await fireEvent.click(screen.getByRole("button", { name: /FASTA.*Sequences/i }));
    await fireEvent.click(screen.getByRole("button", { name: /Detected Cas proteins/i }));
    await waitFor(() => expect(api.downloadArtifact).toHaveBeenCalledWith(
      credential.jobId,
      "fasta",
      credential.accessToken,
    ));
    expect(document.body.textContent).not.toContain(credential.accessToken);
    expect(screen.getByText(/Technical artifacts and complete bundle/i)).toBeInTheDocument();
  });
});

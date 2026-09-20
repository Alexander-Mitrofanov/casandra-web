import { fireEvent, render, screen, waitFor, within } from "@testing-library/vue";
import { describe, expect, it, vi } from "vitest";

import { api } from "../src/api.js";
import ExactTables from "../src/components/results/ExactTables.vue";
import ResultsView from "../src/components/results/ResultsView.vue";
import { cassetteMembers, featureLabel } from "../src/utils/resultTables.js";
import { exampleJob } from "./exampleFixtures.js";

const genome = exampleJob("complete_genome").summary;
const cassetteTable = () => screen.getByRole("table", { name: /Exact Cas cassette coordinates/i });
const geneTable = () => screen.getByRole("table", { name: /Exact Cas protein coordinates/i });

describe("Scientific evidence tables", () => {
  it.each(["complete_genome", "annotate_cas_genes", "classify_cassette", "metagenomic"])("uses the same evidence tables for bundled and completed server jobs in %s", async (mode) => {
    const bundled = exampleJob(mode);
    const describeTables = () => within(screen.getByRole("region", { name: /^(Features and evidence|Protein families and evidence|Cassette evidence)$/ })).getAllByRole("table").map((table) => ({
      caption: table.querySelector("caption").textContent,
      headers: within(table).getAllByRole("columnheader").map((cell) => cell.textContent),
      rows: within(table).getAllByRole("row").map((row) => row.textContent),
    }));
    const bundledView = render(ResultsView, { props: { job: bundled } });
    const expected = describeTables();
    bundledView.unmount();

    const credential = { jobId: bundled.job_id, accessToken: "test-only-private-access-token" };
    const { interactive_results: details, ...serverJob } = bundled;
    serverJob.artifacts = bundled.artifacts.map(({ bundled_path, ...artifact }) => artifact);
    const artifact = serverJob.artifacts.find((row) => row.name === "casandra-results.json");
    let resolveDetails;
    const download = vi.spyOn(api, "downloadArtifact").mockImplementation(() => new Promise((resolve) => { resolveDetails = resolve; }));
    const view = render(ResultsView, { props: { job: { job_id: serverJob.job_id, status: "queued" }, credential } });
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    await view.rerender({ job: serverJob, credential });
    await waitFor(() => expect(download).toHaveBeenCalledWith(serverJob.job_id, artifact.artifact_id, credential.accessToken));
    // Summary tables are usable immediately, while the complete sequence artifact loads.
    expect(describeTables()).toEqual(expected);
    const tables = screen.getByRole("region", { name: /^(Features and evidence|Protein families and evidence|Cassette evidence)$/ });
    const firstButton = within(tables).getAllByRole("button", { name: /^View evidence/ })[0];
    await fireEvent.click(firstButton);
    expect(firstButton).toHaveAttribute("aria-expanded", "true");
    expect(within(tables).getByRole("region", { name: /^Evidence for/ })).toBeVisible();
    await fireEvent.click(firstButton);

    resolveDetails({ size: artifact.size_bytes, text: async () => JSON.stringify(details) });
    const genomeMode = ["complete_genome", "metagenomic"].includes(mode);
    const sequenceName = genomeMode ? "Translated Cas protein sequence" : "Submitted protein sequence";
    await waitFor(() => expect(screen.getByLabelText(sequenceName)).toHaveTextContent(/^M/));
    expect(describeTables()).toEqual(expected);
    expect(document.body.textContent).not.toContain(credential.accessToken);
    view.unmount();
  });

  it("exposes the real II-A family composition and filters its genes without replacing their profile context", async () => {
    render(ExactTables, { props: { summary: genome } });
    const row = within(cassetteTable()).getByRole("row", { name: /Cassette 7 II-A/ });
    expect(row).toHaveTextContent("854,751–860,064");
    expect(row).toHaveTextContent("Cas9 · Cas1 · Cas2");
    const cassette = genome.cassettes.find((item) => item.subtype === "II-A");
    expect(row).toHaveTextContent(cassette.confidence.toFixed(3));
    expect(row).not.toHaveTextContent(`${(cassette.confidence * 100).toFixed(1)}%`);
    await fireEvent.update(screen.getByRole("combobox", { name: "Filter Cas genes by cassette" }), cassette.cassette_id);
    expect(within(geneTable()).getAllByRole("row")).toHaveLength(4);
    const cas9 = within(geneTable()).getByRole("row", { name: /CDS 832 Cas9/ });
    expect(cas9).toHaveTextContent("854,751–858,857");
    expect(cas9).toHaveTextContent("1531.894");
    expect(cas9).toHaveTextContent("Cassette 7");
    expect(within(cas9).getByLabelText("plus strand")).toBeInTheDocument();
    await fireEvent.click(within(cas9).getByRole("button", { name: /View evidence/ }));
    const detail = screen.getByRole("region", { name: /Evidence for CDS 832 on/ });
    expect(within(detail).getByText(cassette.cas_protein_ids[0])).toBeVisible();
    expect(within(detail).getByText("C25_Cas9_2")).toBeVisible();
    expect(within(detail).getByText("Class 2 · Type II · II-C")).toBeVisible();
    expect(within(detail).getByText("1731.894")).toBeVisible();
    expect(within(cassetteTable()).getByRole("row", { name: /Cassette 7 II-A/ })).toBeInTheDocument();
    await fireEvent.click(within(cas9).getByRole("button", { name: /Close evidence/ }));
    expect(screen.queryByRole("region", { name: /Evidence for CDS 832 on/ })).not.toBeInTheDocument();
  });

  it("retains minus-strand coordinate order and keeps unassigned genes as Cas calls", async () => {
    render(ExactTables, { props: { summary: genome } });
    const cassette = genome.cassettes.find((row) => row.subtype === "I-C");
    const row = within(cassetteTable()).getByRole("row", { name: /Cassette 12 I-C/ });
    expect(row).toHaveTextContent("Cas2 · Cas1 · Cas4 · Cas7 · Cas8c · Cas5 · Cas3");
    expect(row).toHaveTextContent("1.000");
    expect(row).not.toHaveTextContent("100%");
    const filter = screen.getByRole("combobox", { name: "Filter Cas genes by cassette" });
    await fireEvent.update(filter, cassette.cassette_id);
    expect(within(geneTable()).getAllByRole("row")).toHaveLength(8);
    expect(within(geneTable()).getAllByLabelText("minus strand")).toHaveLength(7);
    const cas2 = within(geneTable()).getByRole("row", { name: /Cas2/ });
    expect(cas2).toHaveTextContent("1,283,879–1,284,172");
    await fireEvent.update(filter, "unassigned");
    expect(within(geneTable()).getAllByRole("row")).toHaveLength(14);
    expect(within(geneTable()).getByRole("row", { name: /CDS 132 Cas12c/ })).toHaveTextContent("Not assigned");
    expect(within(geneTable()).queryByText("no cas")).not.toBeInTheDocument();
  });

  it("preserves missing scores, coordinates, strand and boundary status without inventing zeros", async () => {
    render(ExactTables, { props: { summary: {
      analysis_mode: "complete_genome", include_crispr_arrays: false,
      cas_proteins: [
        { protein_id: "unknown", cas_family: "Cas9", start: null, end: "", profile_score: null, score_margin: null },
        { protein_id: "zero-score", cas_family: "Cas1", profile_score: 0, score_margin: 0, partial_5prime: false, partial_3prime: false },
      ],
    } } });
    const unknown = within(geneTable()).getByRole("row", { name: /unknown Cas9/ });
    expect(unknown).toHaveTextContent("—–—");
    expect(unknown).not.toHaveTextContent("0.000");
    expect(within(unknown).getByLabelText("strand not reported")).toBeInTheDocument();
    expect(within(unknown).queryByLabelText("plus strand")).not.toBeInTheDocument();
    expect(within(geneTable()).getByRole("row", { name: /zero-score Cas1/ })).toHaveTextContent("0.000");
    await fireEvent.click(within(unknown).getByRole("button"));
    expect(within(screen.getByRole("region", { name: "Evidence for unknown" })).getByText("Not fully reported")).toBeVisible();
  });

  it("distinguishes repeated cassette aliases across metagenomic records", async () => {
    render(ExactTables, { props: { summary: exampleJob("metagenomic").summary } });
    const filter = screen.getByRole("combobox", { name: "Filter Cas genes by cassette" });
    const iia = within(cassetteTable()).getByRole("row", { name: /Cassette 1 II-A/ });
    const ic = within(cassetteTable()).getByRole("row", { name: /Cassette 1 I-C/ });
    expect(iia).toHaveTextContent("spyogenes_type_IIA_locus");
    expect(ic).toHaveTextContent("spyogenes_type_IC_locus");
    const option = within(filter).getByRole("option", { name: "Cassette 1 · II-A · spyogenes_type_IIA_locus" });
    await fireEvent.update(filter, option.value);
    expect(within(geneTable()).getAllByRole("row")).toHaveLength(4);
    expect(within(geneTable()).getByRole("row", { name: /Cas9/ })).toHaveTextContent("spyogenes_type_IIA_locus");
  });

  it("opens only the selected array when IDs repeat on different source records", async () => {
    render(ExactTables, { props: { summary: {
      analysis_mode: "complete_genome", include_crispr_arrays: true,
      crispr_arrays: [
        { array_id: "array_1", contig_id: "source_a", start: 10, end: 50, model_score: 0.6 },
        { array_id: "array_1", contig_id: "source_b", start: 20, end: 80, model_score: 0.9 },
      ],
    } } });
    await fireEvent.click(screen.getByRole("button", { name: "View evidence for array_1 on source_a" }));
    expect(screen.getByRole("region", { name: "Evidence for array_1 on source_a" })).toBeVisible();
    expect(screen.queryByRole("region", { name: "Evidence for array_1 on source_b" })).not.toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "View evidence for array_1 on source_b" }));
    expect(screen.queryByRole("region", { name: "Evidence for array_1 on source_a" })).not.toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Evidence for array_1 on source_b" })).getByText("0.900")).toBeVisible();
  });

  it("reports unavailable family annotations and preserves repeated members", () => {
    const cassette = { cas_gene_count: 4, cas_protein_ids: ["a", "b", "missing"] };
    expect(cassetteMembers(cassette, [{ protein_id: "a", cas_family: "Cas7" }, { protein_id: "b", cas_family: "Cas7" }])).toEqual({
      items: ["Cas7", "Cas7", "Family unavailable"], note: "1 member annotation unavailable",
    });
    expect(featureLabel("SPY_RS04360_cas9")).toBe("SPY_RS04360_cas9");
    expect(featureLabel("custom|cds=000001|anything")).toBe("custom|cds=000001|anything");
  });
});

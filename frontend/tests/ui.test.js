import { fireEvent, render, screen, waitFor, within } from "@testing-library/vue";
import { describe, expect, it, vi } from "vitest";

import { api } from "../src/api.js";
import JobProgress from "../src/components/jobs/JobProgress.vue";
import RecoveryCredential from "../src/components/jobs/RecoveryCredential.vue";
import ExactTables from "../src/components/results/ExactTables.vue";
import GenomeMap from "../src/components/results/GenomeMap.vue";
import HeroHeader from "../src/components/shell/HeroHeader.vue";
import ServiceStatus from "../src/components/shell/ServiceStatus.vue";
import AnalysisForm from "../src/components/submission/AnalysisForm.vue";
import ResultsView from "../src/components/results/ResultsView.vue";
import { exampleFetch, exampleJob } from "./exampleFixtures.js";

const limits = { maxBases: 100_000, maxRecordBases: 0, maxRecords: 10, maxRequestBytes: 1_000_000, maxArtifactBytes: 0, maxHeaderCharacters: 200 };
const credential = { jobId: "0123456789abcdef0123456789abcdef", accessToken: "abcdefghijklmnopqrstuvwxyzABCDEFGH123456789_-", expiresAt: null };
const completeExample = exampleJob("complete_genome");
const metagenomicExample = exampleJob("metagenomic");

describe("CasAndra user interface", () => {
  it.each([
    ["complete_genome", /Complete genome/i, "Run Complete genome example", /spyogenes_type_IIA_complete/, "input.fna", true],
    ["annotate_cas_genes", /Annotate Cas genes/i, "Run Annotate Cas genes example", /SPY_RS04360_cas9/, "input.faa", false],
    ["classify_cassette", /Classify cassette/i, "Run Classify cassette example", /SPY_RS04360_cas9/, "input.faa", false],
    ["metagenomic", /Metagenomic analysis/i, "Run Metagenomic analysis example", /spyogenes_type_IIA_locus/, "input.fna", false],
  ])("loads the selected %s example input, then completes through Run analysis", async (mode, radioName, exampleButton, header, expectedFilename, includeArrays) => {
    const submit = vi.spyOn(api, "submit");
    vi.stubGlobal("fetch", vi.fn(exampleFetch()));
    const view = render(AnalysisForm, {
      props: { service: { state: "offline" }, limits, hasActiveJob: false },
    });
    if (mode !== "complete_genome") await fireEvent.click(screen.getByRole("radio", { name: radioName }));
    await fireEvent.click(screen.getByRole("button", { name: exampleButton }));
    const inputName = ["annotate_cas_genes", "classify_cassette"].includes(mode) ? /Protein FASTA/i : /Nucleotide FASTA/i;
    await waitFor(() => expect(screen.getByRole("textbox", { name: inputName }).value).toMatch(header));
    expect(screen.getByLabelText("Filename")).toHaveValue(expectedFilename);
    expect(view.emitted()["example-completed"]).toBeUndefined();
    const arrays = screen.getByRole("checkbox", { name: /CRISPR array detection/i });
    expect(arrays.closest(".mode-card")).toHaveTextContent("Complete genome");
    if (includeArrays) expect(arrays).toBeChecked();
    else expect(arrays).not.toBeChecked();

    await fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));
    await waitFor(() => expect(view.emitted()["example-completed"]).toHaveLength(1));
    expect(view.emitted()["example-completed"][0][0].summary.analysis_mode).toBe(mode);
    expect(submit).not.toHaveBeenCalled();
  });

  it("submits normally when a loaded example input is edited", async () => {
    vi.stubGlobal("fetch", vi.fn(exampleFetch()));
    const submit = vi.spyOn(api, "submit").mockResolvedValue({
      job: { job_id: credential.jobId, status: "queued", phase: "queued" },
      access_token: credential.accessToken,
    });
    const view = render(AnalysisForm, {
      props: { service: { state: "online" }, limits, hasActiveJob: false },
    });
    await fireEvent.click(screen.getByRole("button", { name: "Run Complete genome example" }));
    const input = screen.getByRole("textbox", { name: /Nucleotide FASTA/i });
    await waitFor(() => expect(input.value).toContain("spyogenes_type_IIA_complete"));
    await fireEvent.update(input, `${input.value}A`);
    await fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));
    expect(submit).toHaveBeenCalledOnce();
    expect(view.emitted()["example-completed"]).toBeUndefined();
  });

  it("shows all feature classes in a source-forward map", () => {
    render(GenomeMap, { props: { summary: completeExample.summary } });
    expect(screen.getByRole("img", { name: /Cas and CRISPR features on spyogenes_type_IIA_complete/i })).toBeInTheDocument();
    expect(screen.getByText("Cas cassette")).toBeInTheDocument();
    expect(screen.getByText(/Cas protein; arrow = strand/)).toBeInTheDocument();
    expect(screen.getByText("CRISPR array")).toBeInTheDocument();
  });

  it("exposes exact accessible tables for cassettes, proteins, and arrays", () => {
    const view = render(ExactTables, { props: { summary: metagenomicExample.summary } });
    const cassetteTable = screen.getByRole("table", { name: /exact Cas cassette coordinates/i });
    expect(within(cassetteTable).getAllByRole("row").length).toBeGreaterThan(1);
    expect(screen.getByRole("table", { name: /exact Cas protein coordinates/i })).toBeInTheDocument();
    view.unmount();
    render(ExactTables, { props: { summary: completeExample.summary } });
    expect(screen.getByRole("table", { name: /exact CRISPRidentify v2 array/i })).toBeInTheDocument();
  });

  it("reports the backend phases without claiming completion early", () => {
    render(JobProgress, {
      props: {
        job: { status: "running", phase: "crispridentify" },
        credential,
      },
    });
    expect(screen.getByRole("heading", { name: "Analysis running" })).toBeInTheDocument();
    expect(screen.getByText("Find CRISPR arrays").closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("Find Cas genes").closest("li")).toHaveClass("complete");
    expect(screen.getByRole("note", { name: /private analysis link/i })).toBeInTheDocument();
  });

  it("shows a larger clean service state without API version copy", () => {
    render(ServiceStatus, { props: { service: { state: "online", version: "0.1.0" } } });
    expect(screen.getByText("Service ready")).toBeInTheDocument();
    expect(screen.queryByText(/API 0\.1\.0/i)).not.toBeInTheDocument();
  });

  it("keeps recovery hidden until an analysis exists", () => {
    render(AnalysisForm, { props: { service: { state: "online" }, limits, hasActiveJob: false } });
    expect(screen.queryByRole("note", { name: /private analysis link/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Already submitted a job/i)).not.toBeInTheDocument();
  });

  it("copies the per-analysis private link with accessible confirmation", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(RecoveryCredential, { props: { credential } });
    await fireEvent.click(screen.getByRole("button", { name: /copy private link/i }));
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("#recover=v1."));
    expect(screen.getByText("Private link copied.")).toBeInTheDocument();
  });

  it("uses the compact pipeline identity and starts with Choose analysis", () => {
    render(HeroHeader, { props: { service: { state: "online" } } });
    expect(screen.getByText("Your Cas predicting oracle")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "CasAndra — Cas proteins detection, annotation and classification pipeline" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Interpretation" })).not.toBeInTheDocument();
    expect(screen.queryByText(/See the Cas system/i)).not.toBeInTheDocument();

    render(AnalysisForm, { props: { service: { state: "online" }, limits, hasActiveJob: false } });
    expect(screen.getByText("Choose analysis")).toBeInTheDocument();
    expect(screen.queryByText("Choose the gene-calling context")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Start with genomic context." })).not.toBeInTheDocument();
  });

  it("offers dedicated step-by-step help for all four modes and scopes arrays to Complete genome", async () => {
    render(AnalysisForm, { props: { service: { state: "online" }, limits, hasActiveJob: false } });
    window.history.replaceState(null, "", "#analysis-choice");
    expect(screen.getAllByRole("radio")).toHaveLength(4);
    expect(screen.getByText("will detect, annotate and classify the Cas genes")).toBeInTheDocument();
    expect(screen.getByText(/Cas family\/profile identity \(for example Cas3 or Cas9\)/i)).toBeInTheDocument();
    const hoverHelp = screen.getByRole("button", { name: "About Complete genome analysis" });
    await fireEvent.mouseEnter(hoverHelp.closest(".info-tooltip"));
    expect(screen.getByRole("region", { name: "About Complete genome analysis" })).toBeInTheDocument();
    await fireEvent.mouseLeave(hoverHelp.closest(".info-tooltip"));
    for (const name of ["About Complete genome analysis", "About Annotate Cas genes analysis", "About Classify cassette analysis", "About Metagenomic analysis"]) {
      const help = screen.getByRole("button", { name });
      expect(help).toHaveAttribute("aria-expanded", "false");
      await fireEvent.click(help);
      const region = screen.getByRole("region", { name });
      expect(within(region).getAllByRole("listitem")).toHaveLength(5);
      expect(help).toHaveAttribute("aria-expanded", "true");
      await fireEvent.keyDown(help, { key: "Escape" });
      expect(screen.queryByRole("region", { name })).not.toBeInTheDocument();
    }
    const arrays = screen.getByRole("checkbox", { name: /complement the analysis with CRISPR array detection/i });
    const completeCard = arrays.closest(".mode-card");
    expect(completeCard).toHaveTextContent("Complete genome");
    expect(completeCard.closest(".mode-grid")).toBeInTheDocument();
    expect(arrays).not.toBeChecked();
    await fireEvent.click(arrays);
    expect(arrays).toBeChecked();
    expect(window.location.hash).toBe("#analysis-choice");
    await fireEvent.click(screen.getByRole("button", { name: "About CRISPRidentify" }));
    expect(screen.getByText(/array proximity does not change or confirm a CasAndra Cas-gene or cassette call/i)).toBeInTheDocument();
    for (const name of [/Annotate Cas genes/i, /Classify cassette/i, /Metagenomic analysis/i]) {
      await fireEvent.click(screen.getByRole("radio", { name }));
      expect(window.location.hash).toBe("#analysis-choice");
      expect(screen.getByRole("checkbox", { name: /CRISPR array detection/i })).not.toBeChecked();
      expect(screen.getByRole("checkbox", { name: /CRISPR array detection/i }).closest(".mode-card")).toBe(completeCard);
    }
    await fireEvent.click(arrays);
    expect(screen.getByRole("radio", { name: /Complete genome/i })).toBeChecked();
    expect(arrays).toBeChecked();
    expect(window.location.hash).toBe("#analysis-choice");
    window.history.replaceState(null, "", window.location.pathname);
  });

  it("switches protein modes to amino-acid input and preserves cassette order copy", async () => {
    render(AnalysisForm, { props: { service: { state: "online" }, limits: { ...limits, maxProteinRecords: 1000, maxResidues: 100_000, maxRecordResidues: 10_000 }, hasActiveJob: false } });
    await fireEvent.click(screen.getByRole("radio", { name: /annotate Cas genes/i }));
    const proteinInput = screen.getByRole("textbox", { name: /Protein FASTA/i });
    expect(screen.getByLabelText("Filename")).toHaveValue("input.faa");
    await fireEvent.update(proteinInput, ">cas3\nMSTNPKPQR*\n>other\nVVVVVV\n");
    expect(screen.getByText("15 aa")).toBeInTheDocument();
    expect(screen.getByText(/every record is analyzed separately/i)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /CRISPR array detection/i })).not.toBeChecked();

    await fireEvent.click(screen.getByRole("radio", { name: /classify cassette/i }));
    expect(screen.getByText(/record order is preserved/i)).toBeInTheDocument();
    expect(screen.getByText(/Ordered protein set → CRISPR type/i)).toBeInTheDocument();
  });

  it("submits the selected analysis mode as the authoritative request option", async () => {
    const submit = vi.spyOn(api, "submit").mockResolvedValue({
      job: { job_id: credential.jobId, status: "queued", phase: "queued" },
      access_token: credential.accessToken,
    });
    render(AnalysisForm, { props: { service: { state: "online" }, limits, hasActiveJob: false } });
    await fireEvent.click(screen.getByRole("radio", { name: /annotate Cas genes/i }));
    await fireEvent.update(screen.getByRole("textbox", { name: /Protein FASTA/i }), ">cas3\nMSTNPKPQR\n>other\nVVVVVV\n");
    await fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));
    expect(submit).toHaveBeenCalledWith({
      sequence: ">cas3\nMSTNPKPQR\n>other\nVVVVVV\n",
      filename: "input.faa",
      analysis_mode: "annotate_cas_genes",
      include_crispr_arrays: false,
    });
  });

  it("hides CRISPRidentify from progress when the selected pipeline does not run it", () => {
    render(JobProgress, {
      props: {
        job: { status: "running", phase: "indexing", options: { analysis_mode: "annotate_cas_genes", include_crispr_arrays: false } },
        credential,
      },
    });
    expect(screen.getByText("Prepare results").closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("Annotate proteins").closest("li")).toHaveClass("complete");
    expect(screen.queryByText("Find CRISPR arrays")).not.toBeInTheDocument();
  });

  it("renders every protein prediction without genomic coordinate views", () => {
    const job = {
      status: "completed",
      options: { analysis_mode: "annotate_cas_genes", include_crispr_arrays: false },
      artifacts: [],
      summary: {
        schema_version: "2.0.0",
        analysis_mode: "annotate_cas_genes",
        include_crispr_arrays: false,
        overview: { protein_count: 2, total_residues: 18, cas_protein_count: 1, wall_seconds: 1.2 },
        protein_predictions: [
          { protein_id: "cas3", residue_count: 9, is_cas: true, result: "Cas3", class: "1", type: "I", subtype: "I-E", profile: "Cas3", profile_score: 42, score_margin: 4.2 },
          { protein_id: "other", is_cas: false, result: "no cas" },
        ],
        provenance: {},
      },
    };
    render(ResultsView, { props: { job } });
    expect(screen.getByRole("heading", { name: "Protein-level Cas annotations" })).toBeInTheDocument();
    const table = screen.getByRole("table", { name: /primary Cas family or no-cas result.*every submitted protein/i });
    expect(within(table).getByText("cas3")).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Cas family result" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "System context (supplementary)" })).toBeInTheDocument();
    expect(within(table).getAllByText("Cas3")).toHaveLength(1);
    expect(within(table).getByText("I-E")).toBeInTheDocument();
    expect(within(table).getByText("Class 1 · Type I")).toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "Best profile" })).not.toBeInTheDocument();
    expect(within(table).getAllByText("no cas").length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: "Source-forward feature map" })).not.toBeInTheDocument();
    expect(screen.queryByText("CRISPR arrays")).not.toBeInTheDocument();
  });

  it("shows ordered cassette and per-sequence metagenomic result views", () => {
    const cassette = {
      analysis_mode: "classify_cassette",
      include_crispr_arrays: false,
      overview: { protein_count: 3, total_residues: 90, cas_protein_count: 2, wall_seconds: 2 },
      protein_predictions: [{ protein_id: "cas10" }, { protein_id: "other" }, { protein_id: "cas7" }],
      cassette_classification: { result: "III-A", class: "1", type: "III", subtype: "III-A", protein_count: 3, cas_gene_count: 2, method: "ordered", cas_protein_ids: ["cas10", "cas7"] },
      provenance: {},
    };
    const view = render(ExactTables, { props: { summary: cassette } });
    expect(screen.getByRole("table", { name: /ordered putative Cas protein set/i })).toBeInTheDocument();
    expect(screen.getByText("cas10 → other → cas7")).toBeInTheDocument();
    expect(screen.getByText("cas10 → cas7")).toBeInTheDocument();
    view.unmount();

    render(ExactTables, { props: { summary: {
      analysis_mode: "metagenomic",
      include_crispr_arrays: false,
      sequence_results: [{ sequence_id: "contig_a", length_bp: 1200, gene_count: 8, cas_gene_count: 2, cassette_count: 1 }],
      cassettes: [], cas_proteins: [], crispr_arrays: [],
    } } });
    const sequences = screen.getByRole("table", { name: /independent Cas gene results for every submitted metagenomic sequence/i });
    expect(within(sequences).getByText("contig_a")).toBeInTheDocument();
    expect(within(sequences).getByText("1,200 bp")).toBeInTheDocument();
    expect(screen.queryByText("CRISPR arrays")).not.toBeInTheDocument();
  });

  it("distinguishes a no-cas cassette and an array detector that was not requested", () => {
    const cassetteView = render(ExactTables, { props: { summary: {
      analysis_mode: "classify_cassette",
      include_crispr_arrays: false,
      protein_predictions: [{ protein_id: "other", is_cas: false, result: "no cas", residue_count: 20 }],
      cassette_classification: { result: "no cas", protein_count: 1, cas_gene_count: 0, cas_protein_ids: [] },
    } } });
    const result = screen.getAllByText("no cas").find((node) => node.classList.contains("prediction-pill"));
    expect(result).toHaveClass("not-cas");
    expect(screen.queryByText("Unresolved")).not.toBeInTheDocument();
    cassetteView.unmount();

    render(ExactTables, { props: { summary: {
      analysis_mode: "complete_genome",
      include_crispr_arrays: false,
      cassettes: [], cas_proteins: [], crispr_arrays: [],
    } } });
    expect(screen.getByText("CRISPR array detection was not requested for this analysis.")).toBeInTheDocument();
    expect(screen.queryByText("CRISPRidentify was requested and found no CRISPR arrays.")).not.toBeInTheDocument();
  });
});

import { fireEvent, render, screen, within } from "@testing-library/vue";
import { describe, expect, it } from "vitest";

import { api } from "../src/api.js";
import JobProgress from "../src/components/jobs/JobProgress.vue";
import RecoveryCredential from "../src/components/jobs/RecoveryCredential.vue";
import ExactTables from "../src/components/results/ExactTables.vue";
import GenomeMap from "../src/components/results/GenomeMap.vue";
import HeroHeader from "../src/components/shell/HeroHeader.vue";
import ServiceStatus from "../src/components/shell/ServiceStatus.vue";
import AnalysisForm from "../src/components/submission/AnalysisForm.vue";
import ResultsView from "../src/components/results/ResultsView.vue";
import { SAMPLE_JOB } from "../src/sample.js";

const limits = { maxBases: 100_000, maxRecordBases: 0, maxRecords: 10, maxRequestBytes: 1_000_000, maxArtifactBytes: 0, maxHeaderCharacters: 200 };
const credential = { jobId: "0123456789abcdef0123456789abcdef", accessToken: "abcdefghijklmnopqrstuvwxyzABCDEFGH123456789_-", expiresAt: null };

describe("CasAndra user interface", () => {
  it("loads the local sample without requiring an online service", async () => {
    const view = render(AnalysisForm, {
      props: { service: { state: "offline" }, limits, hasActiveJob: false },
    });
    await fireEvent.click(screen.getByRole("button", { name: /explore illustrative mock/i }));
    expect(view.emitted()["sample-loaded"][0][0]).toBe(SAMPLE_JOB);
    expect(screen.getByLabelText(/nucleotide fasta/i).value).toContain(">NC_demo_001");
  });

  it("shows all feature classes in a source-forward map", () => {
    render(GenomeMap, { props: { summary: SAMPLE_JOB.summary } });
    expect(screen.getByRole("img", { name: /Cas and CRISPR features on NC_demo_001/i })).toBeInTheDocument();
    expect(screen.getByText("Cas cassette")).toBeInTheDocument();
    expect(screen.getByText(/Cas protein; arrow = strand/)).toBeInTheDocument();
    expect(screen.getByText("CRISPR array")).toBeInTheDocument();
  });

  it("exposes exact accessible tables for cassettes, proteins, and arrays", () => {
    render(ExactTables, { props: { summary: SAMPLE_JOB.summary } });
    const cassetteTable = screen.getByRole("table", { name: /exact Cas cassette coordinates/i });
    expect(within(cassetteTable).getByText("cassette_001")).toBeInTheDocument();
    expect(within(cassetteTable).getByText("2,335")).toBeInTheDocument();
    expect(within(cassetteTable).getByText("0.940")).toBeInTheDocument();
    expect(within(cassetteTable).queryByText("94.0%")).not.toBeInTheDocument();
    expect(within(cassetteTable).getAllByText(/Coordinate proximity only/)).toHaveLength(2);
    expect(screen.getByRole("table", { name: /exact Cas protein coordinates/i })).toBeInTheDocument();
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

  it("offers four analysis modes with accessible CasAndra and CRISPRidentify help", async () => {
    render(AnalysisForm, { props: { service: { state: "online" }, limits, hasActiveJob: false } });
    expect(screen.getAllByRole("radio")).toHaveLength(4);
    expect(screen.getByText("will detect, annotate and classify the Cas genes")).toBeInTheDocument();
    expect(screen.getByText(/Cas family\/profile identity \(for example Cas3 or Cas9\)/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "About CasAndra" })).toHaveAttribute("aria-describedby", "analysis-mode-help-complete_genome");
    expect(screen.getByRole("button", { name: "About CRISPRidentify" })).toHaveAttribute("aria-describedby", "crispridentify-help");
    const arrays = screen.getByRole("checkbox", { name: /complement the analysis with CRISPR array detection/i });
    expect(arrays).not.toBeChecked();
    await fireEvent.click(arrays);
    expect(arrays).toBeChecked();
    expect(screen.getByText(/array proximity does not change or confirm CasAndra’s Cas calls/i)).toBeInTheDocument();
  });

  it("switches protein modes to amino-acid input and preserves cassette order copy", async () => {
    render(AnalysisForm, { props: { service: { state: "online" }, limits: { ...limits, maxProteinRecords: 1000, maxResidues: 100_000, maxRecordResidues: 10_000 }, hasActiveJob: false } });
    await fireEvent.click(screen.getByRole("radio", { name: /annotate Cas genes/i }));
    const proteinInput = screen.getByRole("textbox", { name: /Protein FASTA/i });
    expect(screen.getByLabelText("Filename")).toHaveValue("proteins.faa");
    await fireEvent.update(proteinInput, ">cas3\nMSTNPKPQR*\n>other\nVVVVVV\n");
    expect(screen.getByText("15 aa")).toBeInTheDocument();
    expect(screen.getByText(/every record is analyzed separately/i)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /CRISPR array detection/i })).not.toBeInTheDocument();

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
    await fireEvent.click(screen.getByRole("button", { name: "Start analysis" }));
    expect(submit).toHaveBeenCalledWith({
      sequence: ">cas3\nMSTNPKPQR\n>other\nVVVVVV\n",
      filename: "proteins.faa",
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

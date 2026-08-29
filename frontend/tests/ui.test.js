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
const fullGenomeLimits = { ...limits, maxBases: 2_000_000, maxRequestBytes: 4_500_000 };
const credential = { jobId: "0123456789abcdef0123456789abcdef", accessToken: "abcdefghijklmnopqrstuvwxyzABCDEFGH123456789_-", expiresAt: null };
const completeExample = exampleJob("complete_genome");
const metagenomicExample = exampleJob("metagenomic");

describe("CasAndra user interface", () => {
  it.each([
    ["complete_genome", /Complete genome/i, "Test Complete genome example", /NC_002737\.2_complete_genome/, false],
    ["annotate_cas_genes", /Annotate Cas genes/i, "Test Annotate Cas genes example", /SPY_RS04360_cas9/, false],
    ["classify_cassette", /Classify cassette/i, "Test Classify cassette example", /SPY_RS04360_cas9/, false],
    ["metagenomic", /Metagenomic analysis/i, "Test Metagenomic analysis example", /spyogenes_type_IIA_locus/, false],
  ])("loads the selected %s example input, then completes through Run analysis", async (mode, radioName, exampleButton, header, includeArrays) => {
    const submit = vi.spyOn(api, "submit");
    vi.stubGlobal("fetch", vi.fn(exampleFetch()));
    const view = render(AnalysisForm, {
      props: { service: { state: "offline" }, limits: mode === "complete_genome" ? fullGenomeLimits : limits, hasActiveJob: false },
    });
    if (mode !== "complete_genome") await fireEvent.click(screen.getByRole("radio", { name: radioName }));
    await fireEvent.click(screen.getByRole("button", { name: exampleButton }));
    const inputName = ["annotate_cas_genes", "classify_cassette"].includes(mode) ? /Protein FASTA/i : /Nucleotide FASTA/i;
    await waitFor(() => expect(screen.getByRole("textbox", { name: inputName }).value).toMatch(header));
    expect(screen.queryByLabelText("Filename")).not.toBeInTheDocument();
    expect(view.emitted()["example-completed"]).toBeUndefined();
    const arrays = screen.getByRole("checkbox", { name: /CRISPR array detection/i });
    expect(arrays.closest(".mode-card")).toHaveTextContent("Complete genome");
    if (includeArrays) expect(arrays).toBeChecked();
    else expect(arrays).not.toBeChecked();

    await fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));
    await waitFor(() => expect(view.emitted()["example-completed"]).toHaveLength(1));
    const completed = view.emitted()["example-completed"][0][0];
    expect(completed.summary.analysis_mode).toBe(mode);
    expect(completed.options.include_crispr_arrays).toBe(false);
    expect(completed.summary.include_crispr_arrays).toBe(false);
    expect(submit).not.toHaveBeenCalled();
  });

  it("preserves an enabled CRISPR option and does not substitute the arrays-off snapshot", async () => {
    vi.stubGlobal("fetch", vi.fn(exampleFetch()));
    const submit = vi.spyOn(api, "submit").mockResolvedValue({
      job: { job_id: credential.jobId, status: "queued", phase: "queued" },
      access_token: credential.accessToken,
    });
    const view = render(AnalysisForm, {
      props: { service: { state: "online" }, limits: fullGenomeLimits, hasActiveJob: false },
    });
    const arrays = screen.getByRole("checkbox", { name: /CRISPR array detection/i });
    await fireEvent.click(arrays);
    expect(arrays).toBeChecked();
    await fireEvent.click(screen.getByRole("button", { name: "Test Complete genome example" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: /Nucleotide FASTA/i }).value).toContain("NC_002737.2_complete_genome"));
    expect(arrays).toBeChecked();

    await fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({ include_crispr_arrays: true }));
    expect(view.emitted()["example-completed"]).toBeUndefined();
  });

  it("submits normally when a loaded example input is edited", async () => {
    vi.stubGlobal("fetch", vi.fn(exampleFetch()));
    const submit = vi.spyOn(api, "submit").mockResolvedValue({
      job: { job_id: credential.jobId, status: "queued", phase: "queued" },
      access_token: credential.accessToken,
    });
    const view = render(AnalysisForm, {
      props: { service: { state: "online" }, limits: fullGenomeLimits, hasActiveJob: false },
    });
    await fireEvent.click(screen.getByRole("button", { name: "Test Complete genome example" }));
    const input = screen.getByRole("textbox", { name: /Nucleotide FASTA/i });
    await waitFor(() => expect(input.value).toContain("NC_002737.2_complete_genome"));
    await fireEvent.update(input, `${input.value}A`);
    await fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));
    expect(submit).toHaveBeenCalledOnce();
    expect(view.emitted()["example-completed"]).toBeUndefined();
  });

  it("keeps the arrays-off complete example free of CRISPR tracks and exposes Type II-A", async () => {
    const sourceId = completeExample.summary.contigs[0].id;
    const view = render(GenomeMap, { props: { summary: completeExample.summary, showCrisprArrays: false } });
    expect(screen.getByRole("img", { name: new RegExp(`Cas features on ${sourceId}`) })).toBeInTheDocument();
    expect(screen.getByText("Cas cassette")).toBeInTheDocument();
    expect(screen.getByText(/Cas protein; arrow = strand/)).toBeInTheDocument();
    expect(screen.queryByText("CRISPR array")).not.toBeInTheDocument();
    const cassettePicker = screen.getByRole("group", { name: `Cas cassettes on ${sourceId}` });
    const typeIia = within(cassettePicker).getByRole("button", { name: /Select cassette II-A, bases 854,751–860,064/i });
    expect(typeIia).toHaveTextContent("II-A");
    await fireEvent.click(typeIia);
    expect(view.emitted()["feature-selected"].at(-1)[0]).toMatchObject({ kind: "cassette", type: "II", subtype: "II-A" });
  });

  it("keeps dense Cas gene hit targets collision-free and offers exact quick selection", async () => {
    const summary = {
      analysis_mode: "complete_genome",
      contigs: [{ id: "dense-locus", length: 25_000 }],
      cassettes: [],
      crispr_arrays: [],
      cas_proteins: [
        { protein_id: "cas9", contig_id: "dense-locus", start: 10_018, end: 13_857, strand: "+", result: "Cas9", type: "II" },
        { protein_id: "cas1", contig_id: "dense-locus", start: 13_857, end: 14_726, strand: "+", result: "Cas1" },
        { protein_id: "cas2", contig_id: "dense-locus", start: 14_753, end: 15_064, strand: "+", result: "Cas2" },
      ],
    };
    const view = render(GenomeMap, { props: { summary, showCrisprArrays: false } });
    const geneGroups = [...view.container.querySelectorAll('svg [data-feature-kind="cas_gene"]')];
    const targets = geneGroups.map((group) => {
      const hit = group.querySelector("[data-feature-hit]");
      return {
        id: group.getAttribute("data-feature-id"),
        x: Number(hit.getAttribute("x")),
        width: Number(hit.getAttribute("width")),
        height: Number(hit.getAttribute("height")),
      };
    });
    expect(targets.map((target) => target.id)).toEqual(["cas9", "cas1", "cas2"]);
    expect(targets.every((target) => target.height === 58)).toBe(true);
    for (let index = 0; index < targets.length - 1; index += 1) {
      expect(targets[index].x + targets[index].width).toBeLessThanOrEqual(targets[index + 1].x);
    }

    const cas1Group = geneGroups.find((group) => group.getAttribute("data-feature-id") === "cas1");
    const cas2Group = geneGroups.find((group) => group.getAttribute("data-feature-id") === "cas2");
    const cas1Xs = cas1Group.querySelector(".gene-feature").getAttribute("points").split(/[ ,]/).filter(Boolean).map(Number).filter((_, index) => index % 2 === 0);
    expect(Math.min(...cas1Xs)).toBeCloseTo(64 + ((13_857 - 1) / 25_000) * 872);
    expect(Math.max(...cas1Xs)).toBeCloseTo(64 + (14_726 / 25_000) * 872);
    const cas1VisualEnd = Math.max(...cas1Xs);
    const cas2HitStart = Number(cas2Group.querySelector("[data-feature-hit]").getAttribute("x"));
    expect(cas2HitStart).toBeGreaterThan(cas1VisualEnd);

    const quickSelect = screen.getByRole("group", { name: "Cas genes on dense-locus" });
    const quickButtons = within(quickSelect).getAllByRole("button");
    expect(quickButtons).toHaveLength(3);
    expect(quickButtons.every((button) => button.tagName === "BUTTON")).toBe(true);
    await fireEvent.click(within(quickSelect).getByRole("button", { name: /Select Cas1, bases 13,857\u201314,726/i }));
    expect(view.emitted()["feature-selected"].at(-1)[0]).toMatchObject({ protein_id: "cas1", kind: "cas_gene" });
    expect(cas1Group).toHaveAttribute("aria-pressed", "true");

    await fireEvent.click(cas2Group.querySelector("[data-feature-hit]"));
    expect(view.emitted()["feature-selected"].at(-1)[0]).toMatchObject({ protein_id: "cas2", kind: "cas_gene" });
    await fireEvent.keyDown(cas1Group, { key: " " });
    expect(view.emitted()["feature-selected"].at(-1)[0]).toMatchObject({ protein_id: "cas1", kind: "cas_gene" });
  });

  it("exposes exact Cas tables and reports arrays as not requested", () => {
    const view = render(ExactTables, { props: { summary: metagenomicExample.summary } });
    const cassetteTable = screen.getByRole("table", { name: /exact Cas cassette coordinates/i });
    expect(within(cassetteTable).getAllByRole("row").length).toBeGreaterThan(1);
    expect(screen.getByRole("table", { name: /exact Cas protein coordinates/i })).toBeInTheDocument();
    view.unmount();
    render(ExactTables, { props: { summary: completeExample.summary } });
    expect(screen.queryByRole("table", { name: /exact CRISPRidentify v2 array/i })).not.toBeInTheDocument();
    expect(screen.getByText("CRISPR array detection was not requested for this analysis.")).toBeInTheDocument();
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
    expect(screen.getByRole("heading", { name: "CasAndra. Cas proteins detection, annotation and classification pipeline" })).toBeInTheDocument();
    expect(screen.queryByText("Your Cas predicting oracle")).not.toBeInTheDocument();
    expect(screen.queryByText("Cas intelligence, made explorable.")).not.toBeInTheDocument();
    expect(screen.queryByText("Four focused analyses")).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /start analysis|start with a sequence/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Interpretation" })).not.toBeInTheDocument();
    expect(screen.queryByText(/See the Cas system/i)).not.toBeInTheDocument();

    render(AnalysisForm, { props: { service: { state: "online" }, limits, hasActiveJob: false } });
    const analysisTitle = screen.getByText("Choose analysis", { selector: ".mode-section-title span" });
    expect(analysisTitle.closest(".mode-selector")).toBeInTheDocument();
    expect(screen.queryByText("Choose the gene-calling context")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Start with genomic context." })).not.toBeInTheDocument();
  });

  it("keeps examples, help, and submission inside the uncluttered input card", async () => {
    const view = render(AnalysisForm, { props: { service: { state: "online" }, limits, hasActiveJob: false } });
    const inputSection = view.container.querySelector(".input-section");
    expect(inputSection).not.toBeNull();
    expect(within(inputSection).getByRole("button", { name: "Test Complete genome example" })).toBeInTheDocument();
    expect(within(inputSection).getByRole("button", { name: "Input help for Complete genome" })).toBeInTheDocument();
    expect(within(inputSection).getByRole("button", { name: "Run analysis" })).toBeInTheDocument();
    expect(view.container.querySelector(".submit-bar")).toBeNull();
    expect(view.container.querySelector(".submit-step")).toBeNull();
    expect(view.container.querySelector(".privacy-notice")).toBeNull();
    expect(view.container.querySelector(".input-tools")).toBeNull();
    expect(screen.queryByText(/Use non-sensitive research sequence only/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Raw nucleotide FASTA · one or more contigs/i)).not.toBeInTheDocument();

    const help = screen.getByRole("button", { name: "Input help for Complete genome" });
    await fireEvent.mouseEnter(help.closest(".info-tooltip"));
    const region = screen.getByRole("region", { name: "Input help for Complete genome" });
    expect(within(region).getByText(/Raw nucleotide FASTA · one or more contigs/i)).toBeInTheDocument();
    expect(within(region).getByText(/Cas gene detection → annotation → classification/i)).toBeInTheDocument();
    expect(within(region).getByText(/Use non-sensitive research sequence only/i)).toBeInTheDocument();
    await fireEvent.mouseLeave(help.closest(".info-tooltip"));
    expect(screen.queryByRole("region", { name: "Input help for Complete genome" })).not.toBeInTheDocument();
  });

  it("keeps source filenames automatic and preserves an uploaded FASTA name", async () => {
    const submit = vi.spyOn(api, "submit").mockResolvedValue({
      job: { job_id: credential.jobId, status: "queued", phase: "queued" },
      access_token: credential.accessToken,
    });
    render(AnalysisForm, { props: { service: { state: "online" }, limits, hasActiveJob: false } });
    expect(screen.queryByLabelText("Filename")).not.toBeInTheDocument();
    const file = { name: "isolate-42.fna", size: 22, text: vi.fn().mockResolvedValue(">isolate-42\nACGTACGT\n") };
    await fireEvent.change(screen.getByLabelText("Choose FASTA"), { target: { files: [file] } });
    await waitFor(() => expect(screen.getByRole("textbox", { name: /Nucleotide FASTA/i })).toHaveValue(">isolate-42\nACGTACGT\n"));
    await fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({ filename: "isolate-42.fna" }));
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
    expect(screen.queryByLabelText("Filename")).not.toBeInTheDocument();
    await fireEvent.update(proteinInput, ">cas3\nMSTNPKPQR*\n>other\nVVVVVV\n");
    expect(screen.getByText("15 aa")).toBeInTheDocument();
    expect(screen.queryByText(/Protein FASTA · every record is analyzed separately/i)).not.toBeInTheDocument();
    const annotationHelp = screen.getByRole("button", { name: "Input help for Annotate Cas genes" });
    await fireEvent.mouseEnter(annotationHelp.closest(".info-tooltip"));
    expect(within(screen.getByRole("region", { name: "Input help for Annotate Cas genes" })).getByText(/Protein FASTA · every record is analyzed separately/i)).toBeInTheDocument();
    await fireEvent.mouseLeave(annotationHelp.closest(".info-tooltip"));
    expect(screen.getByRole("checkbox", { name: /CRISPR array detection/i })).not.toBeChecked();

    await fireEvent.click(screen.getByRole("radio", { name: /classify cassette/i }));
    expect(screen.queryByText(/Protein FASTA · record order is preserved/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Ordered protein set → CRISPR type/i)).not.toBeInTheDocument();
    const cassetteHelp = screen.getByRole("button", { name: "Input help for Classify cassette" });
    await fireEvent.mouseEnter(cassetteHelp.closest(".info-tooltip"));
    const cassetteRegion = screen.getByRole("region", { name: "Input help for Classify cassette" });
    expect(within(cassetteRegion).getByText(/Protein FASTA · record order is preserved/i)).toBeInTheDocument();
    expect(within(cassetteRegion).getByText(/Ordered protein set → CRISPR type/i)).toBeInTheDocument();
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

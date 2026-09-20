import { render, screen, fireEvent, within, cleanup, waitFor } from "@testing-library/vue";
import DownloadsPanel from "../src/components/results/DownloadsPanel.vue";
import { api } from "../src/api.js";
import ResultsView from "../src/components/results/ResultsView.vue";
import ProteinExplorer from "../src/components/results/ProteinExplorer.vue";
import SpecificityEvidence from "../src/components/results/SpecificityEvidence.vue";
import protein from "./release_fixtures/cap15_annotate_cas_genes.json";
import ordered from "./release_fixtures/cap15_classify_cassette.json";
import genome from "./release_fixtures/cap15_complete_genome.json";
import meta from "./release_fixtures/cap15_metagenomic.json";
import legacy from "./release_fixtures/original_annotate_cas_genes.json";
import { decisionLabel } from "../src/utils/specificity.js";

afterEach(cleanup);
describe("paired-release specificity presentation", () => {
  it("resets withheld pagination for a replacement result and preserves full IDs", async () => {
    const original = genome.summary.withheld_proteins[0];
    const rows = Array.from({ length: 21 }, (_, index) => ({
      ...original, protein_id: `casandra|contig=test|cds=${index + 1}|loc=1-100`,
    }));
    const view = render(SpecificityEvidence, { props: { summary: { ...genome.summary, withheld_proteins: rows } } });
    const region = screen.getByRole("region", { name: "Scrollable withheld genomic proteins table" });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(within(region).getByText("CDS 1")).toBeInTheDocument();
    expect(region.querySelector("details pre").textContent).toContain(rows[0].protein_id);
    await fireEvent.click(screen.getByRole("button", { name: "Next withheld proteins" }));
    expect(within(region).getByText("CDS 21")).toBeInTheDocument();
    await view.rerender({ summary: { ...genome.summary, withheld_proteins: rows.slice(0, 1) } });
    expect(within(region).getByText("CDS 1")).toBeInTheDocument();
    expect(within(region).queryByText("CDS 21")).toBeNull();
  });

  it("keeps supported, original-negative and all three withheld states distinct", async () => {
    render(ProteinExplorer, { props: { summary: protein.summary, details: protein.interactive_results } });
    expect(document.querySelector(".protein-composition-label")).toHaveTextContent("1 supported Cas calls · 1 original-core negatives · 3 withheld calls");
    expect(document.querySelector(".threshold-line")).toBeNull();
    expect(document.querySelector("#protein-plot-title")).toHaveTextContent("Original-core score margins before specificity rules");
    await fireEvent.update(screen.getByLabelText("Calls"), "abstained");
    const marks = document.querySelectorAll(".protein-score-mark");
    expect(marks).toHaveLength(3);
    for (const mark of marks) expect(mark.getAttribute("aria-label")).toContain("Withheld Cas evidence");
    await fireEvent.click(marks[0]);
    expect(screen.getByText(/Inherited specificity rule withheld this call/)).toBeInTheDocument();
    const md = document.querySelector(".feature-metadata");
    expect(md.textContent).not.toContain("Cas12m");
    expect(md.textContent).toContain("-26.849");
    expect(screen.getByText(/No hit \(stored sentinel is not observed evidence\)/)).toBeInTheDocument();
    expect(document.querySelector(".feature-inspector pre").textContent).toContain('"cas_family": "Cas12m"');
    await fireEvent.update(screen.getByLabelText("Calls"), "no_cas");
    expect(document.querySelectorAll(".protein-score-mark")).toHaveLength(1);
    expect(document.querySelector(".protein-score-mark").getAttribute("aria-label")).toContain("Original-core negative");
    await fireEvent.click(document.querySelector(".protein-score-mark"));
    expect(screen.getByText("No positive hit (stored sentinel is not observed evidence)")).toBeInTheDocument();
  });
  it("retains raw evidence in the exact JSON details without restoring rejected heads", () => {
    for (const row of protein.interactive_results.features) {
      if (!row.abstained_from_baseline_Cas_call) continue;
      expect(row.is_cas).toBe(false); expect(row.cas_family).toBeNull();
      expect([row.class,row.type,row.subtype]).toEqual([null,null,null]);
      expect(row.core_original_prediction.is_cas).toBe(true);
      expect(row.repair_evidence).toBeTruthy();
      expect(decisionLabel(row)).toBe("Withheld Cas evidence");
    }
  });
  it.each([ordered, genome, meta])("preserves accepted candidates and separates genomic withheld evidence: $options.analysis_mode", async (job) => {
    render(ResultsView, { props:{job} });
    expect(screen.getByRole("heading",{name:"Specificity decisions"})).toBeInTheDocument();
    const counts=job.summary.specificity_decisions;
    expect(screen.getByText(`${counts.abstained_count} withheld calls`)).toBeInTheDocument();
    if (job.options.analysis_mode!=="classify_cassette") {
      const section=document.querySelector(".specificity-evidence");
      if (job.summary.withheld_proteins.length) expect(section.textContent).toContain("not accepted Cas loci");
      else expect(section.textContent).toContain("0 withheld calls");
      expect(section.textContent).toContain(`${job.summary.withheld_cassette_candidate_count} cassette candidates withheld`);
      expect(job.interactive_results.features.filter(x=>x.kind==="cassette")).toHaveLength(job.summary.cassettes.length);
      const accepted=new Set(job.summary.cas_proteins.map(x=>x.protein_id));
      for (const x of job.summary.withheld_proteins) expect(accepted.has(x.protein_id)).toBe(false);
      expect(job.artifacts.some(x=>x.name.includes("rejected_cassette_candidates"))).toBe(true);
      expect(job.artifacts.some(x=>x.name==="gene-records.jsonl")).toBe(true);
    }
    expect(job.artifacts.some(x=>x.name==="casandra-results.zip")).toBe(true);
  });
  it("makes raw gene evidence, rejected candidates and the complete ZIP downloadable", async () => {
    const token="local-test-token";
    const spy=vi.spyOn(api,"downloadArtifact").mockResolvedValue(new Blob(["fixture"],{type:"application/octet-stream"}));
    vi.spyOn(HTMLAnchorElement.prototype,"click").mockImplementation(()=>{});
    render(DownloadsPanel,{props:{job:genome,credential:{jobId:genome.job_id,accessToken:token}}});
    await fireEvent.click(screen.getByText(/Raw evidence and complete bundle/));
    for (const name of ["protein-predictions.jsonl","gene-records.jsonl","raw-rejected_cassette_candidates.jsonl","casandra-results.zip"]) {
      const button=screen.getByRole("button",{name:new RegExp(`Download ${name.replaceAll(".","\\.")} as`)});
      await fireEvent.click(button);
      const artifact=genome.artifacts.find(x=>x.name===name);
      await waitFor(()=>expect(spy).toHaveBeenLastCalledWith(genome.job_id,artifact.artifact_id,token));
      await waitFor(()=>expect(button).toBeEnabled());
    }
  });
  it("renders the unchanged original rollback result through the same frontend", () => {
    render(ResultsView,{props:{job:legacy}});
    expect(screen.queryByRole("heading",{name:"Specificity decisions"})).toBeNull();
    expect(screen.getByRole("heading",{name:"Protein-level Cas annotations"})).toBeInTheDocument();
    expect(document.querySelector(".threshold-line")).not.toBeNull();
  });
  it("does not label a stored sentinel as measured negative evidence", () => {
    render(SpecificityEvidence,{props:{summary:protein.summary}});
    expect(screen.getByText(/missing negative hit uses a stored sentinel/)).toBeInTheDocument();
    expect(screen.getByText(/not probabilities or final specificity thresholds/)).toBeInTheDocument();
  });
});

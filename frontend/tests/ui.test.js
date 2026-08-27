import { fireEvent, render, screen, within } from "@testing-library/vue";
import { describe, expect, it } from "vitest";

import JobProgress from "../src/components/jobs/JobProgress.vue";
import ExactTables from "../src/components/results/ExactTables.vue";
import GenomeMap from "../src/components/results/GenomeMap.vue";
import AnalysisForm from "../src/components/submission/AnalysisForm.vue";
import { SAMPLE_JOB } from "../src/sample.js";

const limits = { maxBases: 100_000, maxRecordBases: 0, maxRecords: 10, maxRequestBytes: 1_000_000, maxArtifactBytes: 0, maxHeaderCharacters: 200 };

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
        credential: { jobId: "0123456789abcdef0123456789abcdef", accessToken: "a".repeat(43), expiresAt: null },
      },
    });
    expect(screen.getByRole("heading", { name: "Analysis running" })).toBeInTheDocument();
    expect(screen.getByText("Find CRISPR arrays").closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("Find Cas genes").closest("li")).toHaveClass("complete");
  });
});

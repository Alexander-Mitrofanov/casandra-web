<script setup>
import { computed, ref, watch } from "vue";

import { api } from "../../api.js";
import { summaryFromJob } from "../../utils/results.js";
import AppIcon from "../common/AppIcon.vue";
import DownloadsPanel from "./DownloadsPanel.vue";
import ExactTables from "./ExactTables.vue";
import GenomeMap from "./GenomeMap.vue";
import OverviewCards from "./OverviewCards.vue";
import ProteinExplorer from "./ProteinExplorer.vue";

const props = defineProps({
  job: { type: Object, default: null },
  credential: { type: Object, default: null },
  maxArtifactBytes: { type: Number, default: 0 },
});
const summary = computed(() => summaryFromJob(props.job));
const displaySummary = computed(() => {
  if (!summary.value) return null;
  return {
    ...summary.value,
    analysis_mode: summary.value.analysis_mode || props.job?.options?.analysis_mode || "complete_genome",
    include_crispr_arrays: Object.hasOwn(summary.value, "include_crispr_arrays")
      ? Boolean(summary.value.include_crispr_arrays)
      : Object.hasOwn(props.job?.options || {}, "include_crispr_arrays")
        ? Boolean(props.job.options.include_crispr_arrays)
        : false,
  };
});
const analysisMode = computed(() => displaySummary.value?.analysis_mode || "complete_genome");
const proteinMode = computed(() => ["annotate_cas_genes", "classify_cassette"].includes(analysisMode.value));
const interactiveDetails = ref(null);
const detailsLoading = ref(false);
const detailsError = ref("");
let detailRequest = 0;

const detailArtifact = computed(() => (props.job?.artifacts || []).find((artifact) => (
  artifact?.name === "casandra-results.json"
  || (artifact?.role === "results" && artifact?.format === "json" && artifact?.scope === "complete")
)) || null);

function validateInteractiveDetails(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("The complete result artifact is not a JSON object.");
  }
  if (!Array.isArray(value.features) || !Array.isArray(value.sources)) {
    throw new Error("The complete result artifact is missing its feature or source collection.");
  }
  if (value.features.length > 100_000 || value.sources.length > 100_000) {
    throw new Error("The complete result artifact exceeds the interactive viewer limit.");
  }
  const mode = String(value.analysis_mode || "");
  if (mode && mode !== analysisMode.value) {
    throw new Error("The complete result artifact belongs to a different analysis mode.");
  }
  return value;
}

async function loadInteractiveDetails() {
  if (interactiveDetails.value || detailsLoading.value) return;
  if (props.job?.interactive_results) {
    try {
      interactiveDetails.value = validateInteractiveDetails(props.job?.interactive_results);
    } catch (error) {
      detailsError.value = error.message || "Complete feature details are unavailable.";
    }
    return;
  }
  const artifact = detailArtifact.value;
  const jobId = String(props.job?.job_id || "");
  const token = String(props.credential?.accessToken || "");
  if (!artifact || !jobId || !token || props.credential?.jobId !== jobId) return;
  const artifactBytes = Number(artifact.size_bytes) || 0;
  if (props.maxArtifactBytes > 0 && artifactBytes > props.maxArtifactBytes) {
    detailsError.value = "The complete result is larger than this browser's configured artifact limit. Use the JSON download below.";
    return;
  }

  const request = ++detailRequest;
  detailsLoading.value = true;
  detailsError.value = "";
  try {
    const blob = await api.downloadArtifact(jobId, artifact.artifact_id, token);
    if (request !== detailRequest) return;
    if (props.maxArtifactBytes > 0 && blob.size > props.maxArtifactBytes) {
      throw new Error("The complete result is larger than this browser's configured artifact limit.");
    }
    const parsed = JSON.parse(await blob.text());
    if (request !== detailRequest) return;
    interactiveDetails.value = validateInteractiveDetails(parsed);
  } catch (error) {
    if (request === detailRequest) {
      detailsError.value = error?.message || "The authenticated feature details could not be loaded.";
    }
  } finally {
    if (request === detailRequest) detailsLoading.value = false;
  }
}

watch(
  () => [props.job?.job_id, props.job?.status, detailArtifact.value?.artifact_id, props.credential?.accessToken, props.job?.interactive_results],
  () => {
    detailRequest += 1;
    interactiveDetails.value = null;
    detailsLoading.value = false;
    detailsError.value = "";
    if (props.job?.status === "completed") void loadInteractiveDetails();
  },
  { immediate: true },
);

const headings = Object.freeze({
  complete_genome: { title: "Cas systems in context", detail: "Use the map to orient yourself, then cite or calculate from the exact tables and checksummed artifacts." },
  annotate_cas_genes: { title: "Protein-level Cas annotations", detail: "Every submitted protein is reported separately by its Cas family/profile identity (such as Cas3 or Cas9), or as “no cas”; system class and type remain supplementary context." },
  classify_cassette: { title: "Cassette classification", detail: "The submitted proteins are interpreted together, in FASTA order, as one putative Cas cassette." },
  metagenomic: { title: "Cas genes by metagenomic sequence", detail: "Every submitted nucleotide record is analyzed independently; use the per-sequence table and coordinate map to inspect its calls." },
});
const heading = computed(() => headings[analysisMode.value] || headings.complete_genome);
</script>

<template>
  <section v-if="job?.status === 'completed'" class="results" aria-labelledby="results-heading">
    <div v-if="displaySummary" class="results-heading"><div><p class="eyebrow">Completed analysis</p><h2 id="results-heading" tabindex="-1">{{ heading.title }}</h2><p>{{ heading.detail }}</p></div><span class="schema-badge"><AppIcon name="check" :size="16"/>Schema {{ displaySummary.schema_version || 'unknown' }}</span></div>
    <template v-if="displaySummary">
      <nav class="result-navigation" aria-label="Result sections">
        <a class="result-nav-link" href="#result-overview"><span>01</span><strong>Overview</strong></a>
        <a class="result-nav-link" href="#result-explorer"><span>02</span><strong>Explore results</strong></a>
        <a class="result-nav-link" href="#result-downloads"><span>03</span><strong>Download files</strong></a>
        <a class="result-nav-link" href="#result-tables"><span>04</span><strong>Exact data</strong></a>
      </nav>
      <OverviewCards :overview="displaySummary.overview || {}" :analysis-mode="analysisMode" :protein-predictions="displaySummary.protein_predictions" :cassette-classification="displaySummary.cassette_classification" :include-crispr-arrays="displaySummary.include_crispr_arrays"/>
      <GenomeMap v-if="!proteinMode" :summary="displaySummary" :details="interactiveDetails" :details-loading="detailsLoading" :details-error="detailsError" :show-crispr-arrays="displaySummary.include_crispr_arrays" @details-needed="loadInteractiveDetails"/>
      <ProteinExplorer v-else :summary="displaySummary" :details="interactiveDetails" :details-loading="detailsLoading" :details-error="detailsError" @details-needed="loadInteractiveDetails"/>
      <DownloadsPanel :job="job" :credential="credential" :max-artifact-bytes="maxArtifactBytes"/>
      <ExactTables :summary="displaySummary"/>
    </template>
    <div v-else class="results-missing" role="alert"><AppIcon name="warning"/><div><h2 id="results-heading" tabindex="-1">Result summary unavailable</h2><p>The job completed, but the schema-versioned summary was not included. Download the listed artifacts or report this service inconsistency.</p></div></div>
  </section>
</template>

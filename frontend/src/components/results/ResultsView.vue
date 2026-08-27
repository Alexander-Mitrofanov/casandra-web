<script setup>
import { computed } from "vue";

import { summaryFromJob } from "../../utils/results.js";
import AppIcon from "../common/AppIcon.vue";
import DownloadsPanel from "./DownloadsPanel.vue";
import ExactTables from "./ExactTables.vue";
import GenomeMap from "./GenomeMap.vue";
import OverviewCards from "./OverviewCards.vue";
import ProvenancePanel from "./ProvenancePanel.vue";
import WarningsPanel from "./WarningsPanel.vue";

const props = defineProps({
  job: { type: Object, default: null },
  credential: { type: Object, default: null },
  maxArtifactBytes: { type: Number, default: 0 },
  sample: Boolean,
});
const summary = computed(() => summaryFromJob(props.job));
</script>

<template>
  <section v-if="job?.status === 'completed'" class="results" aria-labelledby="results-heading">
    <div v-if="summary" class="results-heading"><div><p class="eyebrow">{{ sample ? 'Illustrative mock · not computed from the displayed FASTA' : 'Completed analysis' }}</p><h2 id="results-heading" tabindex="-1">Cas systems in context</h2><p>Use the map to orient yourself, then cite or calculate from the exact tables and checksummed artifacts.</p></div><span class="schema-badge"><AppIcon name="check" :size="16"/>Schema {{ summary.schema_version || 'unknown' }}</span></div>
    <template v-if="summary"><OverviewCards :overview="summary.overview || {}"/><GenomeMap :summary="summary"/><ExactTables :summary="summary"/><WarningsPanel :warnings="summary.warnings"/><DownloadsPanel :job="job" :credential="credential" :max-artifact-bytes="maxArtifactBytes" :sample="sample"/><ProvenancePanel :provenance="summary.provenance" :schema-version="summary.schema_version"/></template>
    <div v-else class="results-missing" role="alert"><AppIcon name="warning"/><div><h2 id="results-heading" tabindex="-1">Result summary unavailable</h2><p>The job completed, but the schema-versioned summary was not included. Download the listed artifacts or report this service inconsistency.</p></div></div>
  </section>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";

import AnalysisForm from "./components/submission/AnalysisForm.vue";
import JobProgress from "./components/jobs/JobProgress.vue";
import ResultsView from "./components/results/ResultsView.vue";
import HeroHeader from "./components/shell/HeroHeader.vue";
import { useJobSession } from "./composables/useJobSession.js";
import { useServiceConfig } from "./composables/useServiceConfig.js";
import { clearJobRecoveryLink, parseJobRecoveryLink } from "./jobStore.js";

const { service, limits, refresh } = useServiceConfig();
const {
  credential,
  job,
  sampleJob,
  pollError,
  cancelling,
  onSubmitted,
  onResumed,
  onSampleLoaded,
  cancel,
  forget,
} = useJobSession();

const recoveryLinkError = ref("");

function resumeFromPrivateLink() {
  let nextCredential;
  try {
    nextCredential = parseJobRecoveryLink(window.location.href);
    if (!nextCredential) return;
    recoveryLinkError.value = "";
    onResumed(nextCredential);
  } catch (error) {
    recoveryLinkError.value = error.message || "This private analysis link is invalid.";
  } finally {
    clearJobRecoveryLink(window);
  }
}

onMounted(() => {
  resumeFromPrivateLink();
  window.addEventListener("hashchange", resumeFromPrivateLink);
});
onBeforeUnmount(() => window.removeEventListener("hashchange", resumeFromPrivateLink));
</script>

<template>
  <div id="top" class="site-shell">
    <HeroHeader :service="service" @refresh="refresh"/>
    <main id="main-content">
      <AnalysisForm :service="service" :limits="limits" :has-active-job="Boolean(credential)" @submitted="onSubmitted" @sample-loaded="onSampleLoaded"/>
      <p v-if="recoveryLinkError" class="poll-error" role="alert">{{ recoveryLinkError }}</p>
      <div v-if="sampleJob" id="sample-result" class="result-anchor"><p class="sr-only" role="status">Illustrative mock result ready; values were not computed from the displayed FASTA.</p><ResultsView :job="sampleJob" sample/></div>
      <div v-if="credential" id="job-status" class="job-anchor"><JobProgress :job="job || { status: 'queued', phase: 'queued' }" :credential="credential" :cancelling="cancelling" @cancel="cancel" @forget="forget"/><ResultsView :job="job" :credential="credential" :max-artifact-bytes="limits.maxArtifactBytes"/></div>
      <p v-if="pollError" class="poll-error" role="alert">{{ pollError }}</p>
    </main>
  </div>
</template>

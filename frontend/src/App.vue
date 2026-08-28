<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";

import AnalysisForm from "./components/submission/AnalysisForm.vue";
import JobProgress from "./components/jobs/JobProgress.vue";
import ResultsView from "./components/results/ResultsView.vue";
import HeroHeader from "./components/shell/HeroHeader.vue";
import SiteFooter from "./components/shell/SiteFooter.vue";
import { useJobSession } from "./composables/useJobSession.js";
import { useServiceConfig } from "./composables/useServiceConfig.js";
import { clearJobRecoveryLink, parseJobRecoveryLink } from "./jobStore.js";

const { service, limits, refresh } = useServiceConfig();
const {
  credential,
  job,
  exampleJob,
  pollError,
  cancelling,
  onSubmitted,
  onResumed,
  onExampleCompleted,
  clearExample,
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
      <AnalysisForm :service="service" :limits="limits" :has-active-job="Boolean(credential)" @submitted="onSubmitted" @example-completed="onExampleCompleted" @example-cleared="clearExample"/>
      <p v-if="recoveryLinkError" class="poll-error" role="alert">{{ recoveryLinkError }}</p>
      <div v-if="exampleJob" id="example-result" class="result-anchor"><p class="sr-only" role="status">Analysis completed.</p><ResultsView :job="exampleJob" :max-artifact-bytes="limits.maxArtifactBytes"/></div>
      <div v-if="credential" id="job-status" class="job-anchor"><JobProgress :job="job || { status: 'queued', phase: 'queued' }" :credential="credential" :cancelling="cancelling" @cancel="cancel" @forget="forget"/><ResultsView :job="job" :credential="credential" :max-artifact-bytes="limits.maxArtifactBytes"/></div>
      <p v-if="pollError" class="poll-error" role="alert">{{ pollError }}</p>
    </main>
    <SiteFooter :service="service"/>
  </div>
</template>

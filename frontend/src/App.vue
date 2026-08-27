<script setup>
import AnalysisForm from "./components/submission/AnalysisForm.vue";
import JobProgress from "./components/jobs/JobProgress.vue";
import ResumeJob from "./components/jobs/ResumeJob.vue";
import ResultsView from "./components/results/ResultsView.vue";
import HeroHeader from "./components/shell/HeroHeader.vue";
import ScienceSection from "./components/shell/ScienceSection.vue";
import SiteFooter from "./components/shell/SiteFooter.vue";
import { useJobSession } from "./composables/useJobSession.js";
import { useServiceConfig } from "./composables/useServiceConfig.js";

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
</script>

<template>
  <div id="top" class="site-shell">
    <HeroHeader :service="service" @refresh="refresh"/>
    <main id="main-content">
      <ResumeJob v-if="!credential" @resume="onResumed"/>
      <AnalysisForm :service="service" :limits="limits" :has-active-job="Boolean(credential)" @submitted="onSubmitted" @sample-loaded="onSampleLoaded"/>
      <div v-if="sampleJob" id="sample-result" class="result-anchor"><p class="sr-only" role="status">Illustrative mock result ready; values were not computed from the displayed FASTA.</p><ResultsView :job="sampleJob" sample/></div>
      <div v-if="credential" id="job-status" class="job-anchor"><JobProgress :job="job || { status: 'queued', phase: 'queued' }" :credential="credential" :cancelling="cancelling" @cancel="cancel" @forget="forget"/><ResultsView :job="job" :credential="credential" :max-artifact-bytes="limits.maxArtifactBytes"/></div>
      <p v-if="pollError" class="poll-error" role="alert">{{ pollError }}</p>
      <ScienceSection/>
    </main>
    <SiteFooter :service="service"/>
  </div>
</template>

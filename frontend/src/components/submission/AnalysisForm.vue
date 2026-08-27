<script setup>
import { computed, ref } from "vue";

import { ApiError, api } from "../../api.js";
import { inspectFasta } from "../../fasta.js";
import { normalizeJobCredential } from "../../jobStore.js";
import { SAMPLE_FASTA, SAMPLE_JOB } from "../../sample.js";
import { buildSubmission } from "../../submission.js";
import AppIcon from "../common/AppIcon.vue";
import FastaInput from "./FastaInput.vue";
import GeneModeSelector from "./GeneModeSelector.vue";
import InputSummary from "./InputSummary.vue";

const props = defineProps({
  service: { type: Object, required: true },
  limits: { type: Object, required: true },
  hasActiveJob: Boolean,
});
const emit = defineEmits(["submitted", "sample-loaded"]);

const geneMode = ref("auto");
const sequence = ref("");
const filename = ref("input.fna");
const submitting = ref(false);
const error = ref("");
let submittingLatch = false;

const inspection = computed(() => inspectFasta(sequence.value, { maxHeaderCharacters: props.limits.maxHeaderCharacters }));
const payload = computed(() => buildSubmission({ sequence: sequence.value, filename: filename.value, geneMode: geneMode.value }));
const requestBytes = computed(() => new TextEncoder().encode(JSON.stringify(payload.value)).byteLength);
const withinLimits = computed(() => (
  (!props.limits.maxRecords || inspection.value.recordCount <= props.limits.maxRecords)
  && (!props.limits.maxBases || inspection.value.baseCount <= props.limits.maxBases)
  && (!props.limits.maxRecordBases || inspection.value.records.every((row) => row.sequence.length <= props.limits.maxRecordBases))
  && (!props.limits.maxRequestBytes || requestBytes.value <= props.limits.maxRequestBytes)
));
const ready = computed(() => inspection.value.valid && withinLimits.value && props.service.state === "online" && !props.hasActiveJob);

function loadSample() {
  if (props.hasActiveJob) return;
  sequence.value = SAMPLE_FASTA;
  filename.value = SAMPLE_JOB.input.filename;
  geneMode.value = SAMPLE_JOB.options.gene_mode;
  error.value = "";
  emit("sample-loaded", SAMPLE_JOB);
}

async function submit() {
  if (!ready.value || submittingLatch) return;
  submittingLatch = true;
  submitting.value = true;
  error.value = "";
  try {
    const response = await api.submit(payload.value);
    const initialJob = response?.job;
    const jobId = initialJob?.job_id;
    if (!jobId || !response?.access_token) throw new ApiError("The service returned an incomplete private job credential.");
    const credential = normalizeJobCredential({
      jobId,
      accessToken: response.access_token,
      expiresAt: initialJob?.expires_at || null,
    });
    emit("submitted", credential, initialJob);
  } catch (submitError) {
    error.value = submitError.message || "The analysis could not be submitted.";
  } finally {
    submittingLatch = false;
    submitting.value = false;
  }
}
</script>

<template>
  <section id="workflow" class="workflow" aria-labelledby="workflow-heading">
    <div class="section-intro"><p class="eyebrow">Run analysis</p><h2 id="workflow-heading">Start with genomic context.</h2><p>Submit nucleotide FASTA. CasAndra focuses on Cas genes and cassettes; CRISPRidentify v2 adds array landmarks to the integrated result.</p></div>
    <form novalidate @submit.prevent="submit">
      <GeneModeSelector v-model="geneMode"/>
      <div class="input-section"><div class="form-section-title"><span><b>2</b> Provide source-forward contigs</span><small>Raw nucleotide sequence is required</small></div><div class="input-layout"><FastaInput v-model:sequence="sequence" v-model:filename="filename" :inspection="inspection" :max-request-bytes="limits.maxRequestBytes" :sample-disabled="hasActiveJob" @load-sample="loadSample"/><InputSummary :inspection="inspection" :limits="limits" :request-bytes="requestBytes" :service="service" :gene-mode="geneMode"/></div></div>
      <div v-if="error" class="submit-error" role="alert"><AppIcon name="warning"/><span>{{ error }}</span></div>
      <div v-if="hasActiveJob" class="active-job-lock" role="status"><AppIcon name="info"/><span><strong>A private job is already open.</strong> Save its recovery JSON and leave or cancel that job before submitting another.</span></div>
      <div class="privacy-notice" role="note" aria-label="Sequence privacy notice"><AppIcon name="shield"/><p><strong>Use non-sensitive research sequence only.</strong> A live submission sends FASTA to the service operator. The illustrative mock is fabricated, bundled locally, and not uploaded. Recovery bearer tokens stay in this tab’s memory unless you explicitly download one; anyone holding that file can retrieve the job until it expires. Do not submit clinical, personal, controlled, or confidential sequence.</p></div>
      <div class="submit-bar"><div><span class="submit-step">3</span><span><strong>CasAndra + CRISPRidentify v2</strong><small>Gene calls → cassette classification → array context → artifacts</small></span></div><button class="primary-button" type="submit" :disabled="!ready || submitting"><span>{{ submitting ? 'Submitting…' : hasActiveJob ? 'Current job still open' : service.state !== 'online' ? 'Service unavailable' : 'Start analysis' }}</span><AppIcon name="arrow"/></button></div>
    </form>
  </section>
</template>

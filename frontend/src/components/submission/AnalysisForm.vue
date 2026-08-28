<script setup>
import { computed, ref, watch } from "vue";

import { ApiError, api } from "../../api.js";
import { inspectFasta } from "../../fasta.js";
import { normalizeJobCredential } from "../../jobStore.js";
import { SAMPLE_FASTA, SAMPLE_JOB } from "../../sample.js";
import { analysisModeDefinition, isProteinAnalysis } from "../../science.js";
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

const analysisMode = ref("complete_genome");
const includeCrisprArrays = ref(false);
const sequence = ref("");
const filename = ref("input.fna");
const submitting = ref(false);
const error = ref("");
let submittingLatch = false;

const mode = computed(() => analysisModeDefinition(analysisMode.value));
const proteinInput = computed(() => isProteinAnalysis(analysisMode.value));
const inspection = computed(() => inspectFasta(sequence.value, {
  maxHeaderCharacters: props.limits.maxHeaderCharacters,
  sequenceType: mode.value.sequenceType,
}));
const payload = computed(() => buildSubmission({
  sequence: sequence.value,
  filename: filename.value,
  analysisMode: analysisMode.value,
  includeCrisprArrays: includeCrisprArrays.value,
}));
const requestBytes = computed(() => new TextEncoder().encode(JSON.stringify(payload.value)).byteLength);
const inputLimits = computed(() => proteinInput.value ? {
  ...props.limits,
  maxRecords: props.limits.maxProteinRecords || props.limits.maxRecords,
  maxBases: props.limits.maxResidues || props.limits.maxBases,
  maxRecordBases: props.limits.maxRecordResidues || props.limits.maxRecordBases,
} : props.limits);
const withinLimits = computed(() => (
  (!inputLimits.value.maxRecords || inspection.value.recordCount <= inputLimits.value.maxRecords)
  && (!inputLimits.value.maxBases || inspection.value.baseCount <= inputLimits.value.maxBases)
  && (!inputLimits.value.maxRecordBases || inspection.value.records.every((row) => row.symbolCount <= inputLimits.value.maxRecordBases))
  && (!props.limits.maxRequestBytes || requestBytes.value <= props.limits.maxRequestBytes)
));
const ready = computed(() => inspection.value.valid && withinLimits.value && props.service.state === "online" && !props.hasActiveJob);
const inputCopy = computed(() => ({
  complete_genome: { title: "Provide complete genome sequences", note: "Raw nucleotide FASTA · one or more contigs" },
  annotate_cas_genes: { title: "Provide protein sequences", note: "Protein FASTA · every record is analyzed separately" },
  classify_cassette: { title: "Provide the putative Cas cassette", note: "Protein FASTA · record order is preserved" },
  metagenomic: { title: "Provide metagenomic sequences", note: "Raw nucleotide FASTA · every contig is analyzed separately" },
})[analysisMode.value]);
const pipelineCopy = computed(() => {
  if (analysisMode.value === "annotate_cas_genes") return { title: "CasAndra protein annotation", detail: "Each protein → Cas family/profile or “no cas” → artifacts" };
  if (analysisMode.value === "classify_cassette") return { title: "CasAndra cassette classification", detail: "Ordered protein set → CRISPR type → artifacts" };
  if (analysisMode.value === "metagenomic") return { title: "CasAndra metagenomic analysis", detail: "Every contig → independent Cas gene detection → artifacts" };
  return includeCrisprArrays.value
    ? { title: "CasAndra + CRISPRidentify", detail: "Cas genes → cassette classification → CRISPR arrays → artifacts" }
    : { title: "CasAndra complete-genome analysis", detail: "Cas gene detection → annotation → classification → artifacts" };
});

watch(analysisMode, (next) => {
  if (next !== "complete_genome") includeCrisprArrays.value = false;
  if (["input.fna", "proteins.faa"].includes(filename.value)) {
    filename.value = isProteinAnalysis(next) ? "proteins.faa" : "input.fna";
  }
  error.value = "";
});

function loadSample() {
  if (props.hasActiveJob) return;
  sequence.value = SAMPLE_FASTA;
  filename.value = SAMPLE_JOB.input.filename;
  analysisMode.value = SAMPLE_JOB.options.analysis_mode || "complete_genome";
  includeCrisprArrays.value = Boolean(SAMPLE_JOB.options.include_crispr_arrays);
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
  <section id="workflow" class="workflow" aria-label="CasAndra analysis">
    <form novalidate @submit.prevent="submit">
      <GeneModeSelector v-model="analysisMode" v-model:include-crispr-arrays="includeCrisprArrays"/>
      <div class="input-section"><div class="form-section-title"><span><b>2</b> {{ inputCopy.title }}</span><small>{{ inputCopy.note }}</small></div><div class="input-layout"><FastaInput v-model:sequence="sequence" v-model:filename="filename" :inspection="inspection" :max-request-bytes="limits.maxRequestBytes" :sample-disabled="hasActiveJob" :sequence-type="proteinInput ? 'protein' : 'nucleotide'" @load-sample="loadSample"/><InputSummary :inspection="inspection" :limits="inputLimits" :request-bytes="requestBytes" :service="service" :analysis-mode="analysisMode"/></div></div>
      <div v-if="error" class="submit-error" role="alert"><AppIcon name="warning"/><span>{{ error }}</span></div>
      <div v-if="hasActiveJob" class="active-job-lock" role="status"><AppIcon name="info"/><span><strong>An analysis is already open.</strong> Save its private link, then leave or cancel that analysis before starting another.</span></div>
      <div class="privacy-notice" role="note" aria-label="Sequence privacy notice"><AppIcon name="shield"/><p><strong>Use non-sensitive research sequence only.</strong> A live submission sends FASTA to the service operator. The illustrative mock is fabricated, bundled locally, and not uploaded. Your private analysis link grants access to the submitted job, so keep it private. Do not submit clinical, personal, controlled, or confidential sequence.</p></div>
      <div class="submit-bar"><div><span class="submit-step">3</span><span><strong>{{ pipelineCopy.title }}</strong><small>{{ pipelineCopy.detail }}</small></span></div><button class="primary-button" type="submit" :disabled="!ready || submitting"><span>{{ submitting ? 'Submitting…' : hasActiveJob ? 'Current job still open' : service.state !== 'online' ? 'Service unavailable' : 'Start analysis' }}</span><AppIcon name="arrow"/></button></div>
    </form>
  </section>
</template>

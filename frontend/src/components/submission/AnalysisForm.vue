<script setup>
import { computed, ref, watch } from "vue";

import { ApiError, api } from "../../api.js";
import { loadExampleInput, loadExampleJob } from "../../examples.js";
import { inspectFasta } from "../../fasta.js";
import { normalizeJobCredential } from "../../jobStore.js";
import { analysisModeDefinition, isProteinAnalysis } from "../../science.js";
import { buildSubmission } from "../../submission.js";
import AppIcon from "../common/AppIcon.vue";
import InfoTooltip from "../common/InfoTooltip.vue";
import FastaInput from "./FastaInput.vue";
import GeneModeSelector from "./GeneModeSelector.vue";
import InputSummary from "./InputSummary.vue";

const props = defineProps({
  service: { type: Object, required: true },
  limits: { type: Object, required: true },
  hasActiveJob: Boolean,
});
const emit = defineEmits(["submitted", "example-completed", "example-cleared"]);

const analysisMode = ref("complete_genome");
const includeCrisprArrays = ref(false);
const sequence = ref("");
const filename = ref("input.fna");
const submitting = ref(false);
const exampleLoading = ref(false);
const error = ref("");
const loadedExampleMode = ref("");
const loadedExampleSignature = ref("");
const shownExampleSignature = ref("");
let submittingLatch = false;
let exampleRequest = 0;

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
const payloadSignature = computed(() => JSON.stringify(payload.value));
const matchesLoadedExample = computed(() => (
  loadedExampleMode.value === analysisMode.value
  && loadedExampleSignature.value
  && loadedExampleSignature.value === payloadSignature.value
));
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
const ready = computed(() => inspection.value.valid && withinLimits.value && (props.service.state === "online" || matchesLoadedExample.value) && !props.hasActiveJob);
const inputCopy = computed(() => ({
  complete_genome: { title: "Provide complete genome sequences", note: "Raw nucleotide FASTA · one or more contigs" },
  annotate_cas_genes: { title: "Provide protein sequences", note: "Protein FASTA · every record is analyzed separately" },
  classify_cassette: { title: "Provide the putative Cas cassette", note: "Protein FASTA · record order is preserved" },
  metagenomic: { title: "Provide metagenomic sequences", note: "Raw nucleotide FASTA · every contig is analyzed separately" },
})[analysisMode.value]);
const pipelineCopy = computed(() => {
  if (analysisMode.value === "annotate_cas_genes") return { title: "CasAndra protein annotation", detail: "Each protein → Cas family/profile or “no cas”" };
  if (analysisMode.value === "classify_cassette") return { title: "CasAndra cassette classification", detail: "Ordered protein set → CRISPR type" };
  if (analysisMode.value === "metagenomic") return { title: "CasAndra metagenomic analysis", detail: "Every contig → independent Cas gene detection" };
  return includeCrisprArrays.value
    ? { title: "CasAndra + CRISPRidentify", detail: "Cas genes → cassette classification → CRISPR arrays" }
    : { title: "CasAndra complete-genome analysis", detail: "Cas gene detection → annotation → classification" };
});

watch(analysisMode, (next) => {
  if (next !== "complete_genome") includeCrisprArrays.value = false;
  if (["input.fna", "input.faa", "proteins.faa"].includes(filename.value)) {
    filename.value = isProteinAnalysis(next) ? "input.faa" : "input.fna";
  }
  error.value = "";
});

watch(payloadSignature, (next) => {
  if (shownExampleSignature.value && next !== shownExampleSignature.value) {
    shownExampleSignature.value = "";
    emit("example-cleared");
  }
});

function clearExampleResult() {
  if (!shownExampleSignature.value) return;
  shownExampleSignature.value = "";
  emit("example-cleared");
}

async function loadExample() {
  if (props.hasActiveJob || exampleLoading.value) return;
  const request = ++exampleRequest;
  const selectedMode = analysisMode.value;
  exampleLoading.value = true;
  error.value = "";
  clearExampleResult();
  try {
    const example = await loadExampleInput(selectedMode);
    if (request !== exampleRequest || analysisMode.value !== selectedMode) return;
    sequence.value = example.sequence;
    filename.value = example.filename;
    loadedExampleMode.value = selectedMode;
    loadedExampleSignature.value = JSON.stringify(buildSubmission({
      sequence: example.sequence,
      filename: example.filename,
      analysisMode: selectedMode,
      includeCrisprArrays: example.includeCrisprArrays,
    }));
  } catch (loadError) {
    loadedExampleMode.value = "";
    loadedExampleSignature.value = "";
    error.value = loadError.message || "The selected example could not be loaded.";
  } finally {
    if (request === exampleRequest) exampleLoading.value = false;
  }
}

async function submit() {
  if (!ready.value || submittingLatch) return;
  submittingLatch = true;
  submitting.value = true;
  error.value = "";
  try {
    if (matchesLoadedExample.value) {
      const expectedSignature = payloadSignature.value;
      const completed = await loadExampleJob(analysisMode.value);
      if (payloadSignature.value !== expectedSignature) throw new Error("The input changed while the example result was loading. Run the analysis again.");
      shownExampleSignature.value = expectedSignature;
      emit("example-completed", completed);
      return;
    }
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
      <div class="input-section" aria-labelledby="input-section-title">
        <div class="form-section-title input-section-title">
          <span id="input-section-title"><b>2</b> {{ inputCopy.title }}</span>
          <div class="input-section-actions">
            <button
              type="button"
              class="input-example-button"
              :disabled="hasActiveJob || exampleLoading"
              :aria-label="`Run ${mode.title} example`"
              @click="loadExample"
            ><AppIcon name="dna" :size="17"/>{{ exampleLoading ? 'Loading example…' : 'Run example' }}</button>
            <InfoTooltip tooltip-id="analysis-input-help" :label="`Input help for ${mode.title}`">
              <strong>{{ mode.title }} input and workflow</strong>
              <p>{{ mode.helpIntro }}</p>
              <ol><li v-for="step in mode.helpSteps" :key="step">{{ step }}</li></ol>
              <p><b>Input:</b> {{ inputCopy.note }}. Choose a plain-text {{ proteinInput ? '.faa, .fa, or .fasta' : '.fna, .fa, or .fasta' }} file, drag it into the upload area, or paste FASTA records.</p>
              <p><b>Analysis:</b> {{ pipelineCopy.title }}. {{ pipelineCopy.detail }}.</p>
              <p><b>Actions:</b> Run example loads the matching public reference input. Run analysis processes the input currently shown in this card.</p>
              <p class="tooltip-note"><b>Sequence privacy:</b> Use non-sensitive research sequence only. Custom FASTA is sent to the service operator when analysis begins. A private analysis link grants access to its submitted job, so keep it private. Do not submit clinical, personal, controlled, or confidential sequence.</p>
            </InfoTooltip>
          </div>
        </div>
        <div class="input-layout">
          <FastaInput v-model:sequence="sequence" v-model:filename="filename" :inspection="inspection" :max-request-bytes="limits.maxRequestBytes" :sequence-type="proteinInput ? 'protein' : 'nucleotide'"/>
          <InputSummary :inspection="inspection" :limits="inputLimits" :request-bytes="requestBytes" :analysis-mode="analysisMode"/>
        </div>
        <div v-if="error" class="submit-error" role="alert"><AppIcon name="warning"/><span>{{ error }}</span></div>
        <div v-if="hasActiveJob" class="active-job-lock" role="status"><AppIcon name="info"/><span><strong>An analysis is already open.</strong> Save its private link, then leave or cancel that analysis before starting another.</span></div>
        <div class="input-submit-row">
          <button class="primary-button" type="submit" :disabled="!ready || submitting"><span>{{ submitting ? 'Running…' : hasActiveJob ? 'Current job still open' : service.state !== 'online' && !matchesLoadedExample ? 'Service unavailable' : 'Run analysis' }}</span><AppIcon name="arrow"/></button>
        </div>
      </div>
    </form>
  </section>
</template>

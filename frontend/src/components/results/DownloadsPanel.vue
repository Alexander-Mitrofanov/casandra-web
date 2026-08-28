<script setup>
import { computed, ref, watch } from "vue";

import { api } from "../../api.js";
import { saveBlob } from "../../utils/download.js";
import { asArray, downloadName, readableBytes } from "../../utils/formatting.js";
import AppIcon from "../common/AppIcon.vue";

const props = defineProps({
  job: { type: Object, required: true },
  credential: { type: Object, default: null },
  maxArtifactBytes: { type: Number, default: 0 },
  sample: Boolean,
});
const artifacts = computed(() => asArray(props.job?.artifacts).map((artifact) => {
  const name = String(artifact?.name || "");
  const suffix = name.split(".").pop()?.toLowerCase();
  const format = artifact?.format || ({ faa: "fasta", fna: "fasta", fasta: "fasta", json: "json", csv: "csv", zip: "zip", tsv: "tsv", gff3: "gff3" }[suffix] || "other");
  const preferredNames = new Set([
    "casandra-results.json", "casandra-results.csv", "all-proteins.faa",
    "cassette-proteins.faa", "cassette-cas-proteins.faa", "cas-proteins.faa",
    "cas-coding-sequences.fna", "crispr-arrays.fna", "crispr-components.fna",
  ]);
  return {
    ...artifact,
    format,
    role: artifact?.role || (preferredNames.has(name) ? (format === "fasta" ? "sequences" : "results") : name === "casandra-results.zip" ? "bundle" : "technical"),
  };
}));
const preferred = computed(() => artifacts.value.filter((artifact) => ["results", "sequences"].includes(artifact.role) && ["fasta", "csv", "json"].includes(artifact.format)));
const formats = computed(() => ["fasta", "csv", "json"].filter((format) => preferred.value.some((artifact) => artifact.format === format)));
const selectedFormat = ref("json");
const selectedArtifacts = computed(() => preferred.value.filter((artifact) => artifact.format === selectedFormat.value));
const technicalArtifacts = computed(() => artifacts.value.filter((artifact) => !preferred.value.includes(artifact)));
const downloading = ref("");
const error = ref("");
let downloadLatch = false;

watch(formats, (available) => {
  if (!available.includes(selectedFormat.value)) selectedFormat.value = available[0] || "json";
}, { immediate: true });

const scopeLabels = Object.freeze({
  all_features: "Complete results",
  all_proteins: "All submitted proteins",
  ordered_cassette_proteins: "All cassette proteins",
  cassette_cas_proteins: "Cas proteins in the cassette",
  cas_proteins: "Detected Cas proteins",
  cas_coding_sequences: "Cas coding sequences",
  crispr_arrays: "CRISPR array intervals",
  crispr_repeats_and_spacers: "CRISPR repeats and spacers",
});

function datasetLabel(artifact) {
  return scopeLabels[artifact?.scope] || String(artifact?.name || artifact?.artifact_id || "Result artifact");
}

function formatLabel(format) {
  return format === "fasta" ? "FASTA" : String(format || "file").toUpperCase();
}

async function download(artifact) {
  if (!props.credential || downloadLatch) return;
  const id = String(artifact.artifact_id || "");
  if (!id) return;
  downloadLatch = true;
  downloading.value = id;
  error.value = "";
  try {
    const blob = await api.downloadArtifact(props.credential.jobId, id, props.credential.accessToken);
    saveBlob(blob, downloadName(artifact.name, `${id}.dat`));
  } catch (downloadError) {
    error.value = downloadError.message || "Artifact download failed.";
  } finally {
    downloadLatch = false;
    downloading.value = "";
  }
}
</script>

<template>
  <section class="result-section downloads" aria-labelledby="downloads-heading"><div class="result-heading"><div><p class="eyebrow">Download results</p><h3 id="downloads-heading">Choose a familiar scientific format</h3></div><p>FASTA, CSV, and JSON are generated from the complete validated run. Your private access key is sent only in the authenticated request header.</p></div>
    <p v-if="sample" class="sample-artifact-note"><AppIcon name="info" :size="17"/>This illustrative mock is fabricated to demonstrate the interface and has no remote artifacts. Submit a live job to receive complete FASTA, CSV, JSON, and checksummed technical files.</p>
    <p v-else-if="!artifacts.length" class="sample-artifact-note"><AppIcon name="info" :size="17"/>The service did not list downloadable artifacts for this completed job.</p>
    <template v-else>
      <div v-if="preferred.length" class="preferred-downloads">
        <div class="download-format-picker" role="group" aria-label="Result download format"><button v-for="format in formats" :key="format" type="button" :class="{ selected: selectedFormat === format }" :aria-label="`${formatLabel(format)} · ${format === 'fasta' ? 'Sequences' : format === 'csv' ? 'Spreadsheet' : 'Structured data'}`" :aria-pressed="selectedFormat === format" @click="selectedFormat = format"><b>{{ formatLabel(format) }}</b><span>{{ format === 'fasta' ? 'Sequences' : format === 'csv' ? 'Spreadsheet' : 'Structured data' }}</span></button></div>
        <div class="artifact-list preferred-artifact-list"><button v-for="artifact in selectedArtifacts" :key="artifact.artifact_id" type="button" :aria-label="`Download ${datasetLabel(artifact)} as ${formatLabel(artifact.format)}`" :disabled="Boolean(downloading)" @click="download(artifact)"><span class="artifact-icon"><AppIcon name="file"/><i>{{ formatLabel(artifact.format) }}</i></span><span><strong>{{ datasetLabel(artifact) }}</strong><small>{{ artifact.name }} · {{ readableBytes(artifact.size_bytes) }}</small><code v-if="artifact.sha256">SHA-256 {{ artifact.sha256 }}</code></span><span class="download-action"><AppIcon name="download" :size="17"/>{{ downloading === artifact.artifact_id ? 'Preparing…' : 'Download' }}</span></button></div>
      </div>
      <details v-if="technicalArtifacts.length" class="technical-downloads"><summary><span>Technical artifacts and complete bundle</span><b>{{ technicalArtifacts.length }}</b></summary><p>Validated native reports, provenance, tabular interchange files, and the checksummed ZIP remain available for reproducibility.</p><div class="artifact-list"><button v-for="artifact in technicalArtifacts" :key="artifact.artifact_id" type="button" :aria-label="`Download technical artifact ${artifact.name || artifact.artifact_id}`" :disabled="Boolean(downloading)" @click="download(artifact)"><span class="artifact-icon"><AppIcon name="file"/><i>{{ formatLabel(artifact.format).slice(0, 5) }}</i></span><span><strong>{{ artifact.name || artifact.artifact_id }}</strong><small>{{ artifact.media_type || 'application/octet-stream' }} · {{ readableBytes(artifact.size_bytes) }}</small><code v-if="artifact.sha256">SHA-256 {{ artifact.sha256 }}</code></span><span class="download-action"><AppIcon name="download" :size="17"/>{{ downloading === artifact.artifact_id ? 'Preparing…' : 'Download' }}</span></button></div></details>
    </template>
    <p v-if="maxArtifactBytes && !sample" class="download-memory-note">This browser buffers each authenticated artifact before saving; the configured cap is {{ readableBytes(maxArtifactBytes) }}.</p><p v-if="error" class="download-error" role="alert">{{ error }}</p>
  </section>
</template>

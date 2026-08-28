<script setup>
import { computed, ref } from "vue";

import { api } from "../../api.js";
import { bundledArtifactPath } from "../../examples.js";
import { saveBlob } from "../../utils/download.js";
import { asArray, downloadName, readableBytes } from "../../utils/formatting.js";
import AppIcon from "../common/AppIcon.vue";

const props = defineProps({
  job: { type: Object, required: true },
  credential: { type: Object, default: null },
  maxArtifactBytes: { type: Number, default: 0 },
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
const preferred = computed(() => {
  const order = { json: 0, csv: 1, fasta: 2 };
  return artifacts.value
    .filter((artifact) => ["results", "sequences"].includes(artifact.role) && ["fasta", "csv", "json"].includes(artifact.format))
    .sort((left, right) => (order[left.format] ?? 9) - (order[right.format] ?? 9) || String(left.name).localeCompare(String(right.name)));
});
const availableFormats = computed(() => ["json", "csv", "fasta"]
  .filter((format) => preferred.value.some((artifact) => artifact.format === format)));
const technicalArtifacts = computed(() => artifacts.value.filter((artifact) => !preferred.value.includes(artifact)));
const downloading = ref("");
const error = ref("");
let downloadLatch = false;

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

function saveBundledArtifact(artifact, id) {
  const link = document.createElement("a");
  link.href = bundledArtifactPath(artifact.bundled_path);
  link.download = downloadName(artifact.name, `${id}.dat`);
  link.rel = "noopener";
  document.body.append(link);
  link.click();
  link.remove();
}

async function download(artifact) {
  if (downloadLatch) return;
  const id = String(artifact.artifact_id || artifact.name || "");
  if (!id) return;
  downloadLatch = true;
  downloading.value = id;
  error.value = "";
  try {
    if (artifact.bundled_path) {
      if (props.maxArtifactBytes > 0 && Number(artifact.size_bytes || 0) > props.maxArtifactBytes) throw new Error("This artifact exceeds the browser download limit.");
      saveBundledArtifact(artifact, id);
      return;
    }
    if (!props.credential) throw new Error("This artifact requires the private analysis link used to open the job.");
    const blob = await api.downloadArtifact(props.credential.jobId, id, props.credential.accessToken);
    if (props.maxArtifactBytes > 0 && blob.size > props.maxArtifactBytes) throw new Error("This artifact exceeds the browser download limit.");
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
  <section id="result-downloads" class="result-section downloads" aria-labelledby="downloads-heading"><div class="result-heading"><div><p class="eyebrow">Download results</p><h3 id="downloads-heading">All primary formats, ready to save</h3></div><p>Every available primary-format file is shown together. Downloads never place a private access key in the URL.</p></div>
    <p v-if="!artifacts.length" class="artifact-note"><AppIcon name="info" :size="17"/>The service did not list downloadable artifacts for this completed job.</p>
    <template v-else>
      <div v-if="preferred.length" class="preferred-downloads">
        <p class="download-format-note"><strong v-for="format in availableFormats" :key="format">{{ formatLabel(format) }}</strong><span>Choose any file directly—no format switching required.</span></p>
        <div class="artifact-list preferred-artifact-list"><button v-for="artifact in preferred" :key="artifact.artifact_id" type="button" :aria-label="`Download ${datasetLabel(artifact)} as ${formatLabel(artifact.format)}`" :disabled="Boolean(downloading)" @click="download(artifact)"><span class="artifact-icon"><AppIcon name="file"/><i>{{ formatLabel(artifact.format) }}</i></span><span><strong>{{ datasetLabel(artifact) }}</strong><small>{{ artifact.name }} · {{ readableBytes(artifact.size_bytes) }}</small><code v-if="artifact.sha256">SHA-256 {{ artifact.sha256 }}</code></span><span class="download-action"><AppIcon name="download" :size="17"/>{{ downloading === artifact.artifact_id ? 'Preparing…' : 'Download' }}</span></button></div>
      </div>
      <details v-if="technicalArtifacts.length" class="technical-downloads"><summary><span>Technical artifacts and complete bundle</span><b>{{ technicalArtifacts.length }}</b></summary><p>Validated native reports, provenance, tabular interchange files, and the checksummed ZIP remain available for reproducibility.</p><div class="artifact-list"><button v-for="artifact in technicalArtifacts" :key="artifact.artifact_id" type="button" :aria-label="`Download technical artifact ${artifact.name || artifact.artifact_id}`" :disabled="Boolean(downloading)" @click="download(artifact)"><span class="artifact-icon"><AppIcon name="file"/><i>{{ formatLabel(artifact.format).slice(0, 5) }}</i></span><span><strong>{{ artifact.name || artifact.artifact_id }}</strong><small>{{ artifact.media_type || 'application/octet-stream' }} · {{ readableBytes(artifact.size_bytes) }}</small><code v-if="artifact.sha256">SHA-256 {{ artifact.sha256 }}</code></span><span class="download-action"><AppIcon name="download" :size="17"/>{{ downloading === artifact.artifact_id ? 'Preparing…' : 'Download' }}</span></button></div></details>
    </template>
    <p v-if="maxArtifactBytes" class="download-memory-note">This browser buffers each artifact before saving; the configured cap is {{ readableBytes(maxArtifactBytes) }}.</p><p v-if="error" class="download-error" role="alert">{{ error }}</p>
  </section>
</template>

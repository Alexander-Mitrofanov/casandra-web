<script setup>
import { computed, ref } from "vue";

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
const artifacts = computed(() => asArray(props.job?.artifacts));
const downloading = ref("");
const error = ref("");
let downloadLatch = false;

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
  <section class="result-section downloads" aria-labelledby="downloads-heading"><div class="result-heading"><div><p class="eyebrow">Artifacts</p><h3 id="downloads-heading">Checksummed scientific outputs</h3></div><p>Downloads send the private access key only in the authenticated request header.</p></div>
    <p v-if="sample" class="sample-artifact-note"><AppIcon name="info" :size="17"/>This illustrative mock is fabricated to demonstrate the interface and was not computed from the displayed FASTA. Submit a live job to receive JSON, TSV, GFF3, report, and provenance files.</p>
    <p v-else-if="!artifacts.length" class="sample-artifact-note"><AppIcon name="info" :size="17"/>The service did not list downloadable artifacts for this completed job.</p>
    <div v-else class="artifact-list"><button v-for="artifact in artifacts" :key="artifact.artifact_id" type="button" :disabled="Boolean(downloading)" @click="download(artifact)"><span class="artifact-icon"><AppIcon name="file"/><i>{{ String(artifact.name || 'FILE').split('.').pop().slice(0, 5).toUpperCase() }}</i></span><span><strong>{{ artifact.name || artifact.artifact_id }}</strong><small>{{ artifact.media_type || 'application/octet-stream' }} · {{ readableBytes(artifact.size_bytes) }}</small><code v-if="artifact.sha256">SHA-256 {{ artifact.sha256 }}</code></span><span class="download-action"><AppIcon name="download" :size="17"/>{{ downloading === artifact.artifact_id ? 'Preparing…' : 'Download' }}</span></button></div>
    <p v-if="maxArtifactBytes && !sample" class="download-memory-note">This browser buffers each authenticated artifact before saving; the configured cap is {{ readableBytes(maxArtifactBytes) }}.</p><p v-if="error" class="download-error" role="alert">{{ error }}</p>
  </section>
</template>

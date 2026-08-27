<script setup>
import { serializeJobCredential } from "../../jobStore.js";
import { saveBlob } from "../../utils/download.js";
import AppIcon from "../common/AppIcon.vue";

const props = defineProps({ credential: { type: Object, required: true } });

function download() {
  saveBlob(
    new Blob([serializeJobCredential(props.credential)], { type: "application/json" }),
    `casandra-job-${props.credential.jobId}.recovery.json`,
  );
}
</script>

<template>
  <div class="credential-notice" role="note" aria-label="Private job recovery credential"><AppIcon name="shield"/><div><strong>Save access before closing this tab.</strong><p>The bearer token is held in memory, never in browser storage or the URL.</p></div><button type="button" @click="download"><AppIcon name="download" :size="16"/>Download recovery JSON</button></div>
</template>

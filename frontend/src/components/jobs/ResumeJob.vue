<script setup>
import { ref } from "vue";

import { parseJobCredential } from "../../jobStore.js";
import AppIcon from "../common/AppIcon.vue";

const emit = defineEmits(["resume"]);
const error = ref("");

async function load(event) {
  const [file] = event.target.files || [];
  event.target.value = "";
  if (!file) return;
  if (file.size > 16_384) {
    error.value = "Recovery file exceeds 16 KiB.";
    return;
  }
  try {
    emit("resume", parseJobCredential(await file.text()));
    error.value = "";
  } catch (loadError) {
    error.value = loadError.message || "Recovery file could not be read.";
  }
}
</script>

<template>
  <section class="resume-job" aria-labelledby="resume-heading"><div><p class="eyebrow">Private recovery</p><h2 id="resume-heading">Already submitted a job?</h2><p id="resume-help">Open its recovery JSON locally. The token is sent only as an Authorization header.</p></div><label class="resume-button"><AppIcon name="upload" :size="17"/>Resume job<input type="file" accept=".json,application/json" aria-describedby="resume-help" @change="load"/></label><p v-if="error" class="resume-error" role="alert">{{ error }}</p></section>
</template>

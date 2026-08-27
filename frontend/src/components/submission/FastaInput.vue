<script setup>
import { ref } from "vue";

import AppIcon from "../common/AppIcon.vue";

const props = defineProps({
  sequence: { type: String, required: true },
  filename: { type: String, required: true },
  inspection: { type: Object, required: true },
  maxRequestBytes: { type: Number, default: 0 },
  sampleDisabled: Boolean,
});
const emit = defineEmits(["update:sequence", "update:filename", "load-sample"]);
const fileError = ref("");
const dragging = ref(false);

async function loadFile(file) {
  if (!file) return;
  if (props.maxRequestBytes && file.size > props.maxRequestBytes) {
    fileError.value = `The selected file exceeds the ${Math.round(props.maxRequestBytes / 1_000_000)} MB request limit.`;
    return;
  }
  try {
    const text = await file.text();
    emit("update:sequence", text);
    emit("update:filename", file.name || "input.fna");
    fileError.value = "";
  } catch {
    fileError.value = "The FASTA file could not be read in this browser.";
  }
}

function choose(event) {
  const [file] = event.target.files || [];
  event.target.value = "";
  void loadFile(file);
}

function drop(event) {
  dragging.value = false;
  void loadFile(event.dataTransfer?.files?.[0]);
}
</script>

<template>
  <div class="fasta-input">
    <div :class="['drop-zone', { dragging }]" @dragenter.prevent="dragging = true" @dragover.prevent @dragleave.prevent="dragging = false" @drop.prevent="drop">
      <AppIcon name="upload" :size="28"/>
      <div><strong>Drop nucleotide FASTA here</strong><p>or select a plain-text <code>.fna</code>, <code>.fa</code>, or <code>.fasta</code> file</p></div>
      <label class="file-button">Choose FASTA<input type="file" accept=".fna,.fa,.fasta,.fas,text/plain" @change="choose"/></label>
    </div>
    <div class="input-divider"><span>or paste records</span></div>
    <label class="sequence-label" for="sequence-input"><span>Nucleotide FASTA</span><small>IUPAC DNA symbols · one or more contigs</small></label>
    <textarea id="sequence-input" :value="sequence" spellcheck="false" rows="9" placeholder=">contig_1&#10;ATGCGTACGTTG..." @input="$emit('update:sequence', $event.target.value)"/>
    <div class="input-tools">
      <label>Filename <input :value="filename" maxlength="180" autocomplete="off" @input="$emit('update:filename', $event.target.value)"/></label>
      <button type="button" :disabled="sampleDisabled" @click="$emit('load-sample')"><AppIcon name="dna" :size="17"/>Explore illustrative mock</button>
    </div>
    <p v-if="fileError" class="field-error" role="alert">{{ fileError }}</p>
    <ul v-if="sequence && inspection.errors.length" class="validation-errors" aria-label="FASTA validation errors"><li v-for="error in inspection.errors.slice(0, 5)" :key="error">{{ error }}</li></ul>
  </div>
</template>

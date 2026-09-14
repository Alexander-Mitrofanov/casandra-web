<script setup>
import { computed, ref } from "vue";

import AppIcon from "../common/AppIcon.vue";

const props = defineProps({
  sequence: { type: String, required: true },
  filename: { type: String, required: true },
  inspection: { type: Object, required: true },
  maxRequestBytes: { type: Number, default: 0 },
  sequenceType: { type: String, default: "nucleotide" },
});
const emit = defineEmits(["update:sequence", "update:filename"]);
const fileError = ref("");
const dragging = ref(false);
const protein = computed(() => props.sequenceType === "protein");
const inputName = computed(() => protein.value ? "Protein FASTA" : "Nucleotide FASTA");
const placeholder = computed(() => protein.value
  ? "Drop FASTA here, or paste protein sequences.\n\n>protein_1\nMSTNPKPQRKTK..."
  : "Drop FASTA here, or paste nucleotide sequences.\n\n>sequence_1\nATGCGTACGTTG...");
const acceptedFiles = computed(() => protein.value
  ? ".faa,.fa,.fasta,.fas,text/plain"
  : ".fna,.fa,.fasta,.fas,text/plain");

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
    <div class="fasta-field-heading">
      <label class="sequence-label" for="sequence-input">{{ inputName }}</label>
      <label class="file-button"><AppIcon name="upload" :size="17"/>Choose FASTA<input type="file" :accept="acceptedFiles" @change="choose"/></label>
    </div>
    <div :class="['sequence-editor', { dragging }]" @dragenter.prevent="dragging = true" @dragover.prevent @dragleave.prevent="dragging = false" @drop.prevent="drop">
      <textarea id="sequence-input" :value="sequence" spellcheck="false" rows="10" :aria-invalid="Boolean(sequence && inspection.errors.length)" :aria-describedby="sequence && inspection.errors.length ? 'sequence-validation-errors' : undefined" :placeholder="placeholder" @input="$emit('update:sequence', $event.target.value)"/>
    </div>
    <p v-if="fileError" class="field-error" role="alert">{{ fileError }}</p>
    <ul v-if="sequence && inspection.errors.length" id="sequence-validation-errors" class="validation-errors" aria-label="FASTA validation errors"><li v-for="error in inspection.errors.slice(0, 5)" :key="error">{{ error }}</li></ul>
  </div>
</template>

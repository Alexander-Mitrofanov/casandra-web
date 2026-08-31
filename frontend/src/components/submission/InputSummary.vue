<script setup>
import { computed } from "vue";

import { readableBases, readableResidues } from "../../fasta.js";
import { isProteinAnalysis } from "../../science.js";
import { readableBytes } from "../../utils/formatting.js";
import AppIcon from "../common/AppIcon.vue";

const props = defineProps({
  inspection: { type: Object, required: true },
  limits: { type: Object, required: true },
  requestBytes: { type: Number, required: true },
  analysisMode: { type: String, required: true },
});

const protein = computed(() => isProteinAnalysis(props.analysisMode));
const recordsOk = computed(() => !props.limits.maxRecords || props.inspection.recordCount <= props.limits.maxRecords);
const basesOk = computed(() => !props.limits.maxBases || props.inspection.baseCount <= props.limits.maxBases);
const recordBasesOk = computed(() => !props.limits.maxRecordBases || props.inspection.records.every((row) => row.symbolCount <= props.limits.maxRecordBases));
const requestOk = computed(() => !props.limits.maxRequestBytes || props.requestBytes <= props.limits.maxRequestBytes);
const ready = computed(() => props.inspection.valid && recordsOk.value && basesOk.value && recordBasesOk.value && requestOk.value);
const limitIssues = computed(() => {
  const amount = protein.value ? readableResidues : readableBases;
  const recordLabel = protein.value ? "Protein count" : "Contig count";
  const totalLabel = protein.value ? "Total residues" : "Total bases";
  return [
    !recordsOk.value ? `${recordLabel} exceeds the ${props.limits.maxRecords.toLocaleString()}-record limit.` : null,
    !basesOk.value ? `${totalLabel} exceeds the ${amount(props.limits.maxBases)} limit.` : null,
    !recordBasesOk.value ? `A record exceeds the ${amount(props.limits.maxRecordBases)} per-record limit.` : null,
    !requestOk.value ? `Encoded request exceeds the ${readableBytes(props.limits.maxRequestBytes)} upload limit.` : null,
  ].filter(Boolean);
});
</script>

<template>
  <aside class="input-summary" aria-labelledby="input-summary-heading">
    <h3 id="input-summary-heading">Input check</h3>
    <dl><div><dt>{{ protein ? 'Proteins' : 'Contigs' }}</dt><dd :class="{ bad: !recordsOk }">{{ inspection.recordCount.toLocaleString() }}</dd></div><div><dt>{{ protein ? 'Residues' : 'Bases' }}</dt><dd :class="{ bad: !basesOk || !recordBasesOk }">{{ protein ? readableResidues(inspection.baseCount) : readableBases(inspection.baseCount) }}</dd></div></dl>
    <ul v-if="limitIssues.length" class="input-limit-issues" aria-label="Input limit problems"><li v-for="issue in limitIssues" :key="issue">{{ issue }}</li></ul>
    <div v-if="ready" class="readiness-state ready"><AppIcon name="check" :size="17"/><strong>Ready</strong></div>
  </aside>
</template>

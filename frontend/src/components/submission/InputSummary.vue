<script setup>
import { computed } from "vue";

import { readableBases, readableResidues } from "../../fasta.js";
import { analysisModeDefinition, isProteinAnalysis } from "../../science.js";
import AppIcon from "../common/AppIcon.vue";

const props = defineProps({
  inspection: { type: Object, required: true },
  limits: { type: Object, required: true },
  requestBytes: { type: Number, required: true },
  service: { type: Object, required: true },
  analysisMode: { type: String, required: true },
});

const protein = computed(() => isProteinAnalysis(props.analysisMode));
const mode = computed(() => analysisModeDefinition(props.analysisMode));
const recordsOk = computed(() => !props.limits.maxRecords || props.inspection.recordCount <= props.limits.maxRecords);
const basesOk = computed(() => !props.limits.maxBases || props.inspection.baseCount <= props.limits.maxBases);
const recordBasesOk = computed(() => !props.limits.maxRecordBases || props.inspection.records.every((row) => row.symbolCount <= props.limits.maxRecordBases));
const requestOk = computed(() => !props.limits.maxRequestBytes || props.requestBytes <= props.limits.maxRequestBytes);
</script>

<template>
  <aside class="input-summary" aria-labelledby="input-summary-heading">
    <p class="eyebrow">Preflight</p><h3 id="input-summary-heading">Input readiness</h3>
    <dl><div><dt>{{ protein ? 'Proteins' : 'Contigs' }}</dt><dd :class="{ bad: !recordsOk }">{{ inspection.recordCount.toLocaleString() }}</dd></div><div><dt>{{ protein ? 'Residues' : 'Bases' }}</dt><dd :class="{ bad: !basesOk || !recordBasesOk }">{{ protein ? readableResidues(inspection.baseCount) : readableBases(inspection.baseCount) }}</dd></div><div><dt>Analysis</dt><dd>{{ mode.title }}</dd></div></dl>
    <div :class="['readiness-state', inspection.valid && recordsOk && basesOk && recordBasesOk && requestOk ? 'ready' : 'waiting']"><AppIcon :name="inspection.valid && recordsOk && basesOk && recordBasesOk && requestOk ? 'check' : 'info'" :size="17"/><span><strong>{{ inspection.valid && recordsOk && basesOk && recordBasesOk && requestOk ? `${protein ? 'Protein' : 'Nucleotide'} FASTA is ready` : 'Input needs attention' }}</strong><small>{{ service.state === 'online' ? 'Ready for analysis' : 'Sample exploration remains available offline' }}</small></span></div>
  </aside>
</template>

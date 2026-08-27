<script setup>
import { computed } from "vue";

import { readableBases } from "../../fasta.js";
import { readableBytes } from "../../utils/formatting.js";
import AppIcon from "../common/AppIcon.vue";

const props = defineProps({
  inspection: { type: Object, required: true },
  limits: { type: Object, required: true },
  requestBytes: { type: Number, required: true },
  service: { type: Object, required: true },
  geneMode: { type: String, required: true },
});

const recordsOk = computed(() => !props.limits.maxRecords || props.inspection.recordCount <= props.limits.maxRecords);
const basesOk = computed(() => !props.limits.maxBases || props.inspection.baseCount <= props.limits.maxBases);
const recordBasesOk = computed(() => !props.limits.maxRecordBases || props.inspection.records.every((row) => row.sequence.length <= props.limits.maxRecordBases));
const requestOk = computed(() => !props.limits.maxRequestBytes || props.requestBytes <= props.limits.maxRequestBytes);
</script>

<template>
  <aside class="input-summary" aria-labelledby="input-summary-heading">
    <p class="eyebrow">Preflight</p><h3 id="input-summary-heading">Input readiness</h3>
    <dl><div><dt>Records</dt><dd :class="{ bad: !recordsOk }">{{ inspection.recordCount.toLocaleString() }}</dd></div><div><dt>Nucleotides</dt><dd :class="{ bad: !basesOk || !recordBasesOk }">{{ readableBases(inspection.baseCount) }}</dd></div><div><dt>Request size</dt><dd :class="{ bad: !requestOk }">{{ readableBytes(requestBytes) }}</dd></div><div><dt>Gene mode</dt><dd>{{ geneMode === 'meta' ? 'Meta' : 'Auto' }}</dd></div></dl>
    <div :class="['readiness-state', inspection.valid && recordsOk && basesOk && recordBasesOk && requestOk ? 'ready' : 'waiting']"><AppIcon :name="inspection.valid && recordsOk && basesOk && recordBasesOk && requestOk ? 'check' : 'info'" :size="17"/><span><strong>{{ inspection.valid && recordsOk && basesOk && recordBasesOk && requestOk ? 'FASTA is structurally ready' : 'Input needs attention' }}</strong><small>{{ service.state === 'online' ? 'Service limits applied' : 'Sample exploration remains available offline' }}</small></span></div>
    <p class="coordinate-note"><AppIcon name="table" :size="16"/>All displayed feature coordinates are 1-based, inclusive, and source-forward.</p>
  </aside>
</template>

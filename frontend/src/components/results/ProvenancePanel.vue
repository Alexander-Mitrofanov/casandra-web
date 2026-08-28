<script setup>
import { computed } from "vue";

import { analysisModeDefinition, isProteinAnalysis } from "../../science.js";

const props = defineProps({
  provenance: { type: Object, default: () => ({}) },
  schemaVersion: { type: String, default: "—" },
  analysisMode: { type: String, default: "complete_genome" },
  includeCrisprArrays: Boolean,
});
const mode = computed(() => analysisModeDefinition(props.analysisMode));
const proteinMode = computed(() => isProteinAnalysis(props.analysisMode));
</script>

<template>
  <section class="result-section provenance" aria-labelledby="provenance-heading">
    <div class="result-heading"><div><p class="eyebrow">Reproducibility</p><h3 id="provenance-heading">Model and schema provenance</h3></div><p>Checksums identify exact artifacts and model manifests; they do not anonymize submitted sequence.</p></div>
    <dl>
      <div><dt>Result schema</dt><dd><code>{{ schemaVersion }}</code></dd></div>
      <div><dt>Analysis mode</dt><dd>{{ mode.title }}</dd></div>
      <div><dt>CasAndra bundle</dt><dd><code>{{ provenance.casandra_bundle_id || 'Not reported' }}</code></dd></div>
      <div><dt>Bundle manifest SHA-256</dt><dd><code class="hash">{{ provenance.casandra_manifest_sha256 || 'Not reported' }}</code></dd></div>
      <div v-if="!proteinMode"><dt>Gene caller mode</dt><dd>requested <code>{{ provenance.gene_calling?.requested_mode || 'unknown' }}</code>; selected <code>{{ provenance.gene_calling?.selected_modes?.join(', ') || 'unknown' }}</code></dd></div>
      <div v-if="!proteinMode"><dt>Genetic-code policy</dt><dd>observed per-gene tables <code>{{ Object.entries(provenance.gene_calling?.translation_table_counts || {}).map(([table, count]) => `${table}: ${count}`).join(', ') || 'unknown' }}</code></dd></div>
      <div v-if="analysisMode === 'complete_genome'"><dt>Array detector</dt><dd>{{ includeCrisprArrays ? `CRISPRidentify v${provenance.crispridentify_version || 'unknown'}` : 'Not requested' }}</dd></div>
    </dl>
  </section>
</template>

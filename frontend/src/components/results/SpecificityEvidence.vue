<script setup>
import { computed, ref, watch } from "vue";
import { decisionLabel, reasonLabel } from "../../utils/specificity.js";
import { featureLabel, tablePosition } from "../../utils/resultTables.js";
const props = defineProps({ summary: { type: Object, required: true } });
const decisions = computed(() => props.summary.specificity_decisions);
const page = ref(0);
const withheld = computed(() => props.summary.withheld_proteins || []);
const visible = computed(() => withheld.value.slice(page.value * 20, (page.value + 1) * 20));
watch(() => props.summary, () => { page.value = 0; });
</script>
<template>
  <section v-if="decisions" id="result-specificity" class="result-section specificity-evidence" aria-labelledby="specificity-heading">
    <h3 id="specificity-heading">Specificity decisions</h3>
    <p class="specificity-counts"><strong>{{ decisions.supported_count }} supported Cas calls</strong> · {{ decisions.baseline_negative_count }} original-core negatives · <strong>{{ decisions.abstained_count }} withheld calls</strong></p>
    <p>Withheld calls are abstentions from an original-core Cas prediction. They contribute no accepted protein family, subtype or cassette member. An original-core negative is a separate outcome.</p>
    <p>Profile scores and margins are uncalibrated original-core evidence, not probabilities or final specificity thresholds. A missing negative hit uses a stored sentinel; it is not observed negative evidence.</p>
    <template v-if="withheld.length">
      <h4>Withheld genomic protein evidence</h4>
      <p>Coordinates identify the translated protein; these rows are not accepted Cas loci. Complete records, bank scores and domains are in the raw downloads.</p>
      <p class="specificity-scroll-note">Scroll the table horizontally to see every column. Open a row’s evidence for its full protein ID.</p>
      <div class="specificity-table-wrap" tabindex="0" role="region" aria-label="Scrollable withheld genomic proteins table">
        <table aria-label="Withheld genomic proteins">
          <thead><tr><th scope="col">Protein and source</th><th scope="col">Position</th><th scope="col">Decision</th><th scope="col">Original-core family</th><th scope="col">Reason</th></tr></thead>
          <tbody><tr v-for="row in visible" :key="row.protein_id">
            <th scope="row"><strong>{{ featureLabel(row.protein_id) }}</strong><small>{{ row.contig_id }}</small></th>
            <td>{{ tablePosition(row) }} ({{ row.strand }})</td>
            <td>{{ decisionLabel(row) }}</td>
            <td>{{ row.core_original_prediction?.cas_family || 'Not reported' }}</td>
            <td>{{ reasonLabel(row) }}<details><summary>Original evidence and rule details</summary><pre>{{ JSON.stringify({ protein_id: row.protein_id, core_original_prediction: row.core_original_prediction, repair_evidence: row.repair_evidence }, null, 2) }}</pre></details></td>
          </tr></tbody>
        </table>
      </div>
      <div v-if="withheld.length > 20" class="result-pagination" aria-label="Withheld protein pages"><button type="button" :disabled="page === 0" @click="page--">Previous withheld proteins</button><span aria-live="polite">Page {{ page + 1 }} of {{ Math.ceil(withheld.length / 20) }}</span><button type="button" :disabled="(page + 1) * 20 >= withheld.length" @click="page++">Next withheld proteins</button></div>
      <p v-if="summary.detail_truncated?.withheld_proteins">The interactive list is bounded; the raw gene records contain every withheld protein.</p>
    </template>
    <details v-if="summary.withheld_cassette_candidate_count !== undefined"><summary>{{ summary.withheld_cassette_candidate_count }} cassette candidates withheld by the genome gate</summary><p>These are retained diagnostic candidates, not accepted loci. All accepted candidates remain in the map and exact tables; complete rejected records are downloadable.</p><ul><li v-for="row in summary.withheld_cassette_candidates" :key="row.cassette_id"><code>{{ row.cassette_id }}</code>: {{ row.genome_evidence_gate?.rule || 'Gate reason unavailable' }}.</li></ul><p v-if="summary.detail_truncated?.withheld_cassette_candidates">The interactive list is bounded; download all rejected candidates.</p></details>
  </section>
</template>

<script setup>
import { computed } from "vue";

import { asArray, evidenceScore } from "../../utils/formatting.js";

const props = defineProps({ summary: { type: Object, required: true } });
const analysisMode = computed(() => props.summary.analysis_mode || "complete_genome");
const exactHeading = computed(() => ({
  annotate_cas_genes: "Cas family results and evidence",
  classify_cassette: "Cassette classification and evidence",
})[analysisMode.value] || "Feature coordinates and evidence");
const predictions = computed(() => asArray(props.summary.protein_predictions));
const classification = computed(() => props.summary.cassette_classification || {});
const sequenceResults = computed(() => asArray(props.summary.sequence_results));
const arraysRequested = computed(() => {
  if (analysisMode.value !== "complete_genome") return false;
  if (Object.hasOwn(props.summary, "include_crispr_arrays")) return Boolean(props.summary.include_crispr_arrays);
  return true;
});

const typeLabel = (row) => row?.subtype || row?.type || "Unresolved";
const coordinate = (value) => Number.isFinite(Number(value)) ? Number(value).toLocaleString() : "—";
const partialLabel = (row) => {
  if (row.partial_5prime && row.partial_3prime) return "5′ + 3′";
  if (row.partial_5prime) return "5′";
  if (row.partial_3prime) return "3′";
  return "No";
};
const gateAccepted = (row) => {
  const gate = row.evidence_gate;
  return gate && typeof gate === "object" ? Boolean(gate.accepted) : gate === "passed" || gate === true;
};
const gateLabel = (row) => {
  const gate = row.evidence_gate;
  if (gate && typeof gate === "object") return `${gate.accepted ? "Accepted" : "Rejected"}${gate.rule ? ` · ${gate.rule}` : ""}`;
  if (gate === "passed" || gate === true) return "Accepted";
  if (typeof gate === "string") return gate;
  return "Not reported";
};
const nearestArray = (row) => {
  const nearest = row.nearest_array;
  if (!nearest?.array_id) return "—";
  const distance = Number(nearest.distance_bp);
  return `${nearest.array_id}${Number.isFinite(distance) ? ` · ${distance.toLocaleString()} bp` : ""}`;
};
const proteinFamilyLabel = (row) => {
  const result = String(row?.result || "").trim();
  if (result) return result.toLowerCase() === "no cas" ? "no cas" : result;
  if (row?.is_cas === false) return "no cas";
  return String(row?.profile || "").trim() || "unclassified cas";
};
const predictionIsCas = (row) => row?.is_cas !== false && proteinFamilyLabel(row) !== "no cas";
const systemContextLabel = (row) => row?.subtype || row?.type || (row?.class ? `Class ${row.class}` : "");
const systemContextDetail = (row) => {
  const details = [];
  if (row?.class && systemContextLabel(row) !== `Class ${row.class}`) details.push(`Class ${row.class}`);
  if (row?.type && row.type !== systemContextLabel(row)) details.push(`Type ${row.type}`);
  return details.join(" · ");
};
const classificationLabel = (row) => row?.result || row?.subtype || row?.type || "unclassified";
const classificationIsCas = (row) => classificationLabel(row).toLowerCase() !== "no cas" && Number(row?.cas_gene_count || 0) > 0;
</script>

<template>
  <section id="result-tables" class="result-section exact-tables" aria-labelledby="exact-heading">
    <div class="result-heading">
      <div><p class="eyebrow">Exact data</p><h3 id="exact-heading">{{ exactHeading }}</h3></div>
      <p v-if="analysisMode === 'annotate_cas_genes'">Each primary result is a Cas family/profile identity such as Cas3 or Cas9, or exact “no cas”. CRISPR system class/type/subtype is supplementary context.</p>
      <p v-else-if="analysisMode === 'classify_cassette'">The classification applies to the submitted protein set in FASTA order; no genomic coordinates are inferred.</p>
      <p v-else>Every interval is 1-based and inclusive on the submitted source record. Sort or re-index downloaded artifacts for large analyses.</p>
    </div>

    <template v-if="analysisMode === 'annotate_cas_genes'">
      <details open><summary><span>Protein family results</span><b>{{ predictions.length }}</b></summary><div class="table-scroll"><table><caption class="sr-only">Primary Cas family or no-cas result, supplementary system context, and model evidence for every submitted protein</caption><thead><tr><th scope="col">Protein</th><th scope="col" class="numeric">Residues</th><th scope="col">Cas family result</th><th scope="col">System context (supplementary)</th><th scope="col">Profile evidence score</th><th scope="col" class="numeric">Score margin</th></tr></thead><tbody><tr v-for="row in predictions" :key="row.protein_id"><th scope="row"><code>{{ row.protein_id }}</code></th><td class="numeric">{{ Number.isFinite(Number(row.residue_count)) ? `${Number(row.residue_count).toLocaleString()} aa` : '—' }}</td><td><span :class="['prediction-pill', predictionIsCas(row) ? 'cas' : 'not-cas']">{{ proteinFamilyLabel(row) }}</span></td><td><template v-if="predictionIsCas(row) && systemContextLabel(row)"><strong>{{ systemContextLabel(row) }}</strong><small v-if="systemContextDetail(row)">{{ systemContextDetail(row) }}</small></template><template v-else>—</template></td><td>{{ evidenceScore(row.profile_score, row.score_is_probability) }}</td><td class="numeric">{{ Number.isFinite(Number(row.score_margin)) ? Number(row.score_margin).toFixed(3) : '—' }}</td></tr><tr v-if="!predictions.length"><td colspan="6" class="empty-cell">No per-protein predictions were reported.</td></tr></tbody></table></div></details>
    </template>

    <template v-else-if="analysisMode === 'classify_cassette'">
      <details open><summary><span>Cassette classification</span><b>{{ classificationLabel(classification) }}</b></summary><div class="table-scroll"><table><caption class="sr-only">CasAndra classification of the ordered putative Cas protein set</caption><thead><tr><th scope="col">Result</th><th scope="col">Class / type</th><th scope="col" class="numeric">Input proteins</th><th scope="col" class="numeric">Cas genes</th><th scope="col">Method</th><th scope="col">Evidence score</th><th scope="col">All input proteins in FASTA order</th><th scope="col">Cas protein IDs</th></tr></thead><tbody><tr><th scope="row"><span :class="['prediction-pill', classificationIsCas(classification) ? 'cas' : 'not-cas']">{{ classificationLabel(classification) }}</span></th><td><template v-if="classificationIsCas(classification)"><strong>{{ typeLabel(classification) }}</strong><small v-if="classification.class">Class {{ classification.class }}</small></template><template v-else>—</template></td><td class="numeric">{{ classification.protein_count ?? '—' }}</td><td class="numeric">{{ classification.cas_gene_count ?? '—' }}</td><td>{{ classification.method || '—' }}</td><td>{{ evidenceScore(classification.confidence, classification.confidence_is_probability) }}</td><td><code>{{ predictions.map((row) => row.protein_id).join(' → ') || '—' }}</code></td><td><code>{{ asArray(classification.cas_protein_ids).join(' → ') || '—' }}</code></td></tr></tbody></table></div></details>
    </template>

    <template v-else>
      <details v-if="analysisMode === 'metagenomic'" open><summary><span>Per-sequence analyses</span><b>{{ sequenceResults.length }}</b></summary><div class="table-scroll"><table><caption class="sr-only">Independent Cas gene results for every submitted metagenomic sequence</caption><thead><tr><th scope="col">Sequence</th><th scope="col" class="numeric">Length</th><th scope="col" class="numeric">Genes</th><th scope="col" class="numeric">Cas genes</th><th scope="col" class="numeric">Cassettes</th></tr></thead><tbody><tr v-for="row in sequenceResults" :key="row.sequence_id"><th scope="row"><code>{{ row.sequence_id }}</code></th><td class="numeric">{{ coordinate(row.length_bp) }} bp</td><td class="numeric">{{ row.gene_count ?? '—' }}</td><td class="numeric">{{ row.cas_gene_count ?? row.cas_protein_count ?? '—' }}</td><td class="numeric">{{ row.cassette_count ?? '—' }}</td></tr><tr v-if="!sequenceResults.length"><td colspan="5" class="empty-cell">No per-sequence result index was reported.</td></tr></tbody></table></div></details>

      <details open><summary><span>Cas cassettes</span><b>{{ asArray(summary.cassettes).length }}</b></summary><div class="table-scroll"><table><caption class="sr-only">Exact Cas cassette coordinates and classifications</caption><thead><tr><th scope="col">Cassette</th><th scope="col">Contig</th><th scope="col" class="numeric">Start</th><th scope="col" class="numeric">End</th><th scope="col" class="numeric">Cas genes</th><th scope="col">Class / type</th><th scope="col">Method</th><th scope="col">Evidence score</th><th scope="col">Evidence gate</th><th v-if="arraysRequested" scope="col">Nearest array</th></tr></thead><tbody><tr v-for="row in asArray(summary.cassettes)" :key="row.cassette_id"><th scope="row"><code>{{ row.cassette_id }}</code></th><td><code>{{ row.contig_id }}</code></td><td class="numeric">{{ coordinate(row.start) }}</td><td class="numeric">{{ coordinate(row.end) }}</td><td class="numeric">{{ row.cas_gene_count }}</td><td><strong>{{ typeLabel(row) }}</strong><small v-if="row.class">Class {{ row.class }}</small></td><td>{{ row.method || '—' }}</td><td>{{ evidenceScore(row.confidence, row.confidence_is_probability) }}</td><td><span :class="['evidence-pill', gateAccepted(row) ? 'passed' : 'review']">{{ gateLabel(row) }}</span></td><td v-if="arraysRequested"><span>{{ nearestArray(row) }}</span><small v-if="row.nearest_array">Coordinate proximity only</small></td></tr><tr v-if="!asArray(summary.cassettes).length"><td :colspan="arraysRequested ? 10 : 9" class="empty-cell">No Cas cassette was reported.</td></tr></tbody></table></div></details>

      <details open><summary><span>Cas proteins</span><b>{{ asArray(summary.cas_proteins).length }}</b></summary><div class="table-scroll"><table><caption class="sr-only">Exact Cas protein coordinates, strands, genetic codes, partial-boundary flags, and model evidence</caption><thead><tr><th scope="col">Protein</th><th scope="col">Contig</th><th scope="col" class="numeric">Start</th><th scope="col" class="numeric">End</th><th scope="col">Strand</th><th scope="col">Partial boundary</th><th scope="col">Genetic code</th><th scope="col">Type</th><th scope="col">Best profile</th><th scope="col" class="numeric">Score margin</th><th scope="col">Cassette</th></tr></thead><tbody><tr v-for="row in asArray(summary.cas_proteins)" :key="row.protein_id"><th scope="row"><code>{{ row.protein_id }}</code></th><td><code>{{ row.contig_id }}</code></td><td class="numeric">{{ coordinate(row.start) }}</td><td class="numeric">{{ coordinate(row.end) }}</td><td><span class="strand" :aria-label="row.strand === '-' ? 'minus strand' : 'plus strand'">{{ row.strand || '?' }}</span></td><td>{{ partialLabel(row) }}</td><td class="numeric">{{ row.translation_table ?? '—' }}</td><td>{{ typeLabel(row) }}</td><td>{{ row.profile || '—' }}</td><td class="numeric">{{ Number.isFinite(Number(row.score_margin)) ? Number(row.score_margin).toFixed(3) : '—' }}</td><td><code>{{ row.cassette_id || '—' }}</code></td></tr><tr v-if="!asArray(summary.cas_proteins).length"><td colspan="11" class="empty-cell">No Cas protein was reported.</td></tr></tbody></table></div></details>

      <details v-if="arraysRequested" open><summary><span>CRISPR arrays</span><b>{{ asArray(summary.crispr_arrays).length }}</b></summary><div class="table-scroll"><table><caption class="sr-only">Exact CRISPRidentify v2 array coordinates and evidence</caption><thead><tr><th scope="col">Array</th><th scope="col">Contig</th><th scope="col" class="numeric">Start</th><th scope="col" class="numeric">End</th><th scope="col">Strand</th><th scope="col">Category</th><th scope="col" class="numeric">Repeats</th><th scope="col" class="numeric">Spacers</th><th scope="col">Evidence score</th></tr></thead><tbody><tr v-for="row in asArray(summary.crispr_arrays)" :key="row.array_id"><th scope="row"><code>{{ row.array_id }}</code></th><td><code>{{ row.contig_id }}</code></td><td class="numeric">{{ coordinate(row.start) }}</td><td class="numeric">{{ coordinate(row.end) }}</td><td><span class="strand">{{ row.strand || '?' }}</span></td><td><span class="array-category">{{ row.category || 'Unclassified' }}</span></td><td class="numeric">{{ row.repeat_count ?? '—' }}</td><td class="numeric">{{ row.spacer_count ?? '—' }}</td><td>{{ evidenceScore(row.model_score, row.model_score_is_probability) }}</td></tr><tr v-if="!asArray(summary.crispr_arrays).length"><td colspan="9" class="empty-cell">CRISPRidentify was requested and found no CRISPR arrays.</td></tr></tbody></table></div></details>
      <p v-else-if="analysisMode === 'complete_genome'" class="analysis-not-requested">CRISPR array detection was not requested for this analysis.</p>
    </template>
  </section>
</template>

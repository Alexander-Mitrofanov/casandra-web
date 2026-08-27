<script setup>
import { asArray, evidenceScore } from "../../utils/formatting.js";

defineProps({ summary: { type: Object, required: true } });
const typeLabel = (row) => row.subtype || row.type || "Unresolved";
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
</script>

<template>
  <section class="result-section exact-tables" aria-labelledby="exact-heading">
    <div class="result-heading"><div><p class="eyebrow">Exact data</p><h3 id="exact-heading">Feature coordinates and evidence</h3></div><p>Every interval is 1-based and inclusive on the submitted source record. Sort or re-index downloaded artifacts for large analyses.</p></div>

    <details open><summary><span>Cas cassettes</span><b>{{ asArray(summary.cassettes).length }}</b></summary><div class="table-scroll"><table><caption class="sr-only">Exact Cas cassette coordinates and classifications</caption><thead><tr><th scope="col">Cassette</th><th scope="col">Contig</th><th scope="col" class="numeric">Start</th><th scope="col" class="numeric">End</th><th scope="col" class="numeric">Cas genes</th><th scope="col">Class / type</th><th scope="col">Method</th><th scope="col">Evidence score</th><th scope="col">Evidence gate</th><th scope="col">Nearest array</th></tr></thead><tbody><tr v-for="row in asArray(summary.cassettes)" :key="row.cassette_id"><th scope="row"><code>{{ row.cassette_id }}</code></th><td><code>{{ row.contig_id }}</code></td><td class="numeric">{{ coordinate(row.start) }}</td><td class="numeric">{{ coordinate(row.end) }}</td><td class="numeric">{{ row.cas_gene_count }}</td><td><strong>{{ typeLabel(row) }}</strong><small v-if="row.class">Class {{ row.class }}</small></td><td>{{ row.method || '—' }}</td><td>{{ evidenceScore(row.confidence, row.confidence_is_probability) }}</td><td><span :class="['evidence-pill', gateAccepted(row) ? 'passed' : 'review']">{{ gateLabel(row) }}</span></td><td><span>{{ nearestArray(row) }}</span><small v-if="row.nearest_array">Coordinate proximity only</small></td></tr><tr v-if="!asArray(summary.cassettes).length"><td colspan="10" class="empty-cell">No Cas cassette was reported.</td></tr></tbody></table></div></details>

    <details open><summary><span>Cas proteins</span><b>{{ asArray(summary.cas_proteins).length }}</b></summary><div class="table-scroll"><table><caption class="sr-only">Exact Cas protein coordinates, strands, genetic codes, partial-boundary flags, and model evidence</caption><thead><tr><th scope="col">Protein</th><th scope="col">Contig</th><th scope="col" class="numeric">Start</th><th scope="col" class="numeric">End</th><th scope="col">Strand</th><th scope="col">Partial boundary</th><th scope="col">Genetic code</th><th scope="col">Type</th><th scope="col">Best profile</th><th scope="col" class="numeric">Score margin</th><th scope="col">Cassette</th></tr></thead><tbody><tr v-for="row in asArray(summary.cas_proteins)" :key="row.protein_id"><th scope="row"><code>{{ row.protein_id }}</code></th><td><code>{{ row.contig_id }}</code></td><td class="numeric">{{ coordinate(row.start) }}</td><td class="numeric">{{ coordinate(row.end) }}</td><td><span class="strand" :aria-label="row.strand === '-' ? 'minus strand' : 'plus strand'">{{ row.strand || '?' }}</span></td><td>{{ partialLabel(row) }}</td><td class="numeric">{{ row.translation_table ?? '—' }}</td><td>{{ typeLabel(row) }}</td><td>{{ row.profile || '—' }}</td><td class="numeric">{{ Number.isFinite(Number(row.score_margin)) ? Number(row.score_margin).toFixed(3) : '—' }}</td><td><code>{{ row.cassette_id || '—' }}</code></td></tr><tr v-if="!asArray(summary.cas_proteins).length"><td colspan="11" class="empty-cell">No Cas protein was reported.</td></tr></tbody></table></div></details>

    <details open><summary><span>CRISPR arrays</span><b>{{ asArray(summary.crispr_arrays).length }}</b></summary><div class="table-scroll"><table><caption class="sr-only">Exact CRISPRidentify v2 array coordinates and evidence</caption><thead><tr><th scope="col">Array</th><th scope="col">Contig</th><th scope="col" class="numeric">Start</th><th scope="col" class="numeric">End</th><th scope="col">Strand</th><th scope="col">Category</th><th scope="col" class="numeric">Repeats</th><th scope="col">Evidence score</th></tr></thead><tbody><tr v-for="row in asArray(summary.crispr_arrays)" :key="row.array_id"><th scope="row"><code>{{ row.array_id }}</code></th><td><code>{{ row.contig_id }}</code></td><td class="numeric">{{ coordinate(row.start) }}</td><td class="numeric">{{ coordinate(row.end) }}</td><td><span class="strand">{{ row.strand || '?' }}</span></td><td><span class="array-category">{{ row.category || 'Unclassified' }}</span></td><td class="numeric">{{ row.repeat_count ?? '—' }}</td><td>{{ evidenceScore(row.model_score, row.model_score_is_probability) }}</td></tr><tr v-if="!asArray(summary.crispr_arrays).length"><td colspan="8" class="empty-cell">No CRISPR array was reported by CRISPRidentify v2.</td></tr></tbody></table></div></details>
  </section>
</template>

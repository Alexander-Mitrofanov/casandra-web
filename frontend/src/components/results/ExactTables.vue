<script setup>
import { computed, ref, watch } from "vue";

import { asArray, classificationMethodLabel, evidenceScore } from "../../utils/formatting.js";
import { arrayRows, cassetteEvidence, cassetteMembers, cassetteRows, featureLabel, geneRows, predictionRows, sourceId, tableNumber } from "../../utils/resultTables.js";
import EvidenceTable from "./EvidenceTable.vue";

const props = defineProps({ summary: { type: Object, required: true } });
const analysisMode = computed(() => props.summary.analysis_mode || "complete_genome");
const proteinMode = computed(() => ["annotate_cas_genes", "classify_cassette"].includes(analysisMode.value));
const exactHeading = computed(() => ({ annotate_cas_genes: "Protein families and evidence", classify_cassette: "Cassette evidence" })[analysisMode.value] || "Features and evidence");
const proteins = computed(() => asArray(props.summary.cas_proteins));
const predictions = computed(() => asArray(props.summary.protein_predictions));
const cassettes = computed(() => asArray(props.summary.cassettes));
const arrays = computed(() => asArray(props.summary.crispr_arrays));
const arraysRequested = computed(() => analysisMode.value === "complete_genome" && (!Object.hasOwn(props.summary, "include_crispr_arrays") || Boolean(props.summary.include_crispr_arrays)));
const sources = computed(() => [...new Set([
  ...asArray(props.summary.contigs).map((row) => row.id),
  ...asArray(props.summary.sequence_results).map((row) => row.sequence_id),
  ...[...cassettes.value, ...proteins.value, ...arrays.value].map(sourceId),
].filter(Boolean))]);
const showSource = computed(() => sources.value.length !== 1);
const truncated = computed(() => Object.values(props.summary.detail_truncated || {}).some(Boolean));
const cassetteFilter = ref("all");
watch(() => props.summary, () => { cassetteFilter.value = "all"; });
const assigned = computed(() => proteins.value.filter((row) => row.cassette_id).length);
const filteredProteins = computed(() => proteins.value.filter((row) => cassetteFilter.value === "all" || (cassetteFilter.value === "unassigned" ? !row.cassette_id : row.cassette_id === cassetteFilter.value)));
const geneEvidence = computed(() => geneRows(filteredProteins.value, showSource.value));
const cassetteData = computed(() => cassetteRows(cassettes.value, proteins.value, showSource.value, arraysRequested.value));
const arrayData = computed(() => arrayRows(arrays.value, showSource.value));
const proteinData = computed(() => predictionRows(predictions.value));
const sequenceData = computed(() => asArray(props.summary.sequence_results).map((row) => ({
  id: row.sequence_id,
  cells: { name: { text: row.sequence_id }, length: { text: `${tableNumber(row.length_bp)} bp` }, genes: { text: tableNumber(row.gene_count) }, cas: { text: tableNumber(row.cas_gene_count ?? row.cas_protein_count) }, cassettes: { text: tableNumber(row.cassette_count) } },
})));
const classificationData = computed(() => {
  const row = props.summary.cassette_classification || {};
  const result = row.result || row.subtype || row.type || "unclassified";
  return [{
    id: "submitted-cassette", label: "submitted cassette",
    cells: {
      result: { text: result, tone: result.toLowerCase() === "no cas" || !(Number(row.cas_gene_count) > 0) ? "not-cas" : "cas" },
      count: { text: tableNumber(row.cas_gene_count), note: `of ${tableNumber(row.protein_count)} input proteins` },
      families: cassetteMembers(row, predictions.value, false),
      method: { text: classificationMethodLabel(row.method) },
      score: { text: evidenceScore(row.confidence, row.confidence_is_probability) },
    },
    details: [
      ...cassetteEvidence(row),
      { label: "Input proteins in FASTA order", value: predictions.value.map((protein) => protein.protein_id).join(" → ") || "Not reported", code: true, wide: true },
      { label: "Cas protein IDs", value: asArray(row.cas_protein_ids).join(" → ") || "None reported", code: true, wide: true },
    ],
  }];
});
const scoreNote = "Scores are model evidence. Percentages are shown only when reported as probabilities.";
const geneColumns = [{ key: "name", label: "Gene" }, { key: "family", label: "Family", kind: "pill" }, { key: "position", label: "Position (bp)" }, { key: "strand", label: "Strand", kind: "strand" }, { key: "cassette", label: "Cassette" }, { key: "score", label: "Profile score", numeric: true }];
const cassetteColumns = [{ key: "name", label: "Cassette" }, { key: "subtype", label: "Subtype", kind: "pill" }, { key: "position", label: "Position (bp)" }, { key: "count", label: "Cas genes", numeric: true }, { key: "families", label: "Families", kind: "families" }, { key: "score", label: "Score", numeric: true }];
const proteinColumns = [{ key: "name", label: "Protein" }, { key: "family", label: "Family", kind: "pill" }, { key: "length", label: "Length (aa)", numeric: true }, { key: "score", label: "Profile score", numeric: true }];
const classificationColumns = [{ key: "result", label: "Result", kind: "pill" }, { key: "count", label: "Cas proteins", numeric: true }, { key: "families", label: "Families", kind: "families" }, { key: "method", label: "Method" }, { key: "score", label: "Score", numeric: true }];
const sequenceColumns = [{ key: "name", label: "Sequence" }, { key: "length", label: "Length", numeric: true }, { key: "genes", label: "Genes", numeric: true }, { key: "cas", label: "Cas genes", numeric: true }, { key: "cassettes", label: "Cassettes", numeric: true }];
const arrayColumns = [{ key: "name", label: "Array" }, { key: "position", label: "Position (bp)" }, { key: "strand", label: "Strand", kind: "strand" }, { key: "category", label: "Category" }, { key: "repeats", label: "Repeats", numeric: true }, { key: "spacers", label: "Spacers", numeric: true }];
</script>

<template>
  <section id="result-tables" class="result-section exact-tables" aria-labelledby="exact-heading">
    <div class="result-heading">
      <div><p class="eyebrow">Exact data</p><h3 id="exact-heading">{{ exactHeading }}</h3></div>
      <p v-if="proteinMode">Cas family calls for every submitted protein. Open a row for supporting evidence and supplementary profile context.</p>
      <p v-else>Cas families, cassette membership and exact locations. Coordinates are 1-based and inclusive on the source record; strand is shown separately.</p>
    </div>
    <p v-if="!proteinMode && sources.length === 1" class="evidence-source">Source record <code>{{ sources[0] }}</code></p>
    <p v-if="truncated" class="evidence-subset">This view contains a subset of the results. Download the complete files for all records.</p>

    <template v-if="proteinMode">
      <EvidenceTable v-if="analysisMode === 'classify_cassette'" heading="Cassette classification" caption="CasAndra classification of the ordered putative Cas protein set" :columns="classificationColumns" :rows="classificationData" note="Families follow FASTA order. This classification applies to the submitted set; no genomic coordinates are inferred."/>
      <EvidenceTable heading="Protein family results" caption="Primary Cas family or no-cas result and model evidence for every submitted protein" :columns="proteinColumns" :rows="proteinData" :note="scoreNote" empty="No per-protein predictions were reported."/>
    </template>
    <template v-else>
      <EvidenceTable v-if="analysisMode === 'metagenomic'" heading="Per-sequence analyses" caption="Independent Cas gene results for every submitted metagenomic sequence" :columns="sequenceColumns" :rows="sequenceData" :expandable="false" empty="No per-sequence result index was reported."/>
      <EvidenceTable heading="Cas cassettes" caption="Exact Cas cassette coordinates, family composition and classifications" :columns="cassetteColumns" :rows="cassetteData" :note="`Families follow source-coordinate order. ${scoreNote}`" empty="No Cas cassette was reported."/>
      <EvidenceTable heading="Cas genes" caption="Exact Cas protein coordinates, families, strands and model evidence" :columns="geneColumns" :rows="geneEvidence" :count="cassetteFilter === 'all' ? proteins.length : `${filteredProteins.length} / ${proteins.length}`" :note="`${assigned} in cassettes · ${proteins.length - assigned} not assigned`" empty="No Cas genes match this selection.">
        <template v-if="proteins.length" #toolbar>
          <label class="evidence-filter">Show genes
            <select v-model="cassetteFilter" aria-label="Filter Cas genes by cassette">
              <option value="all">All Cas genes ({{ proteins.length }})</option>
              <option v-for="row in cassettes" :key="row.cassette_id" :value="row.cassette_id">{{ featureLabel(row.cassette_id) }} · {{ row.subtype || row.type || 'Unresolved' }}{{ showSource ? ` · ${sourceId(row) || 'Source not reported'}` : '' }}</option>
              <option value="unassigned">Not assigned ({{ proteins.length - assigned }})</option>
            </select>
          </label>
        </template>
      </EvidenceTable>
      <EvidenceTable v-if="arraysRequested" heading="CRISPR arrays" caption="Exact CRISPRidentify v2 array coordinates and evidence" :columns="arrayColumns" :rows="arrayData" empty="CRISPRidentify was requested and found no CRISPR arrays."/>
      <p v-else-if="analysisMode === 'complete_genome'" class="analysis-not-requested">CRISPR array detection was not requested for this analysis.</p>
    </template>
  </section>
</template>

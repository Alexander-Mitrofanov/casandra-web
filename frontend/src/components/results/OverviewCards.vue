<script setup>
import { computed } from "vue";

import { readableBases, readableResidues } from "../../fasta.js";
import { asArray, formatDuration, readableNumber } from "../../utils/formatting.js";

const props = defineProps({
  overview: { type: Object, required: true },
  analysisMode: { type: String, default: "complete_genome" },
  proteinPredictions: { type: Array, default: () => [] },
  cassetteClassification: { type: Object, default: () => ({}) },
  includeCrisprArrays: Boolean,
});
const proteinCount = computed(() => props.overview.protein_count ?? asArray(props.proteinPredictions).length);
const casProteinCount = computed(() => props.overview.cas_protein_count ?? asArray(props.proteinPredictions).filter((row) => row?.is_cas).length);
const noCasCount = computed(() => Math.max(0, Number(proteinCount.value || 0) - Number(casProteinCount.value || 0)));
const classification = computed(() => props.cassetteClassification.result || props.cassetteClassification.subtype || props.cassetteClassification.type || "unclassified");
</script>

<template>
  <dl v-if="analysisMode === 'annotate_cas_genes'" class="overview-cards">
    <div><dt>Proteins inspected</dt><dd>{{ readableNumber(proteinCount) }}</dd><small>independent model inputs</small></div>
    <div><dt>Cas proteins</dt><dd>{{ readableNumber(casProteinCount) }}</dd><small>family/profile calls</small></div>
    <div><dt>no cas</dt><dd>{{ readableNumber(noCasCount) }}</dd><small>negative model calls</small></div>
    <div><dt>Protein sequence</dt><dd>{{ readableResidues(overview.total_residues) }}</dd><small>amino-acid residues</small></div>
    <div><dt>CasAndra time</dt><dd>{{ formatDuration(overview.wall_seconds) }}</dd><small>{{ readableNumber(proteinCount) }} proteins analyzed</small></div>
  </dl>

  <dl v-else-if="analysisMode === 'classify_cassette'" class="overview-cards">
    <div><dt>Input proteins</dt><dd>{{ readableNumber(cassetteClassification.protein_count ?? overview.protein_count) }}</dd><small>FASTA order preserved</small></div>
    <div><dt>Cas genes</dt><dd>{{ readableNumber(cassetteClassification.cas_gene_count ?? overview.cas_protein_count) }}</dd><small>contributing model calls</small></div>
    <div><dt>Classification</dt><dd class="result-value">{{ classification }}</dd><small>CRISPR type</small></div>
    <div><dt>Method</dt><dd class="result-value">{{ cassetteClassification.method || '—' }}</dd><small>classification strategy</small></div>
    <div><dt>CasAndra time</dt><dd>{{ formatDuration(overview.wall_seconds) }}</dd><small>{{ readableResidues(overview.total_residues) }} inspected</small></div>
  </dl>

  <dl v-else-if="analysisMode === 'metagenomic'" class="overview-cards">
    <div><dt>Cas proteins</dt><dd>{{ readableNumber(overview.cas_protein_count) }}</dd><small>sequence-model calls</small></div>
    <div><dt>Cas cassettes</dt><dd>{{ readableNumber(overview.cassette_count) }}</dd><small>metagenomic neighborhoods</small></div>
    <div><dt>Sequences analyzed</dt><dd>{{ readableNumber(overview.contig_count) }}</dd><small>processed independently</small></div>
    <div><dt>Nucleotide sequence</dt><dd>{{ readableBases(overview.total_bases) }}</dd><small>across all source records</small></div>
    <div><dt>CasAndra time</dt><dd>{{ formatDuration(overview.wall_seconds) }}</dd><small>{{ readableNumber(overview.gene_count) }} genes inspected</small></div>
  </dl>

  <dl v-else class="overview-cards">
    <div><dt>Cas proteins</dt><dd>{{ readableNumber(overview.cas_protein_count) }}</dd><small>sequence-model calls</small></div>
    <div><dt>Cas cassettes</dt><dd>{{ readableNumber(overview.cassette_count) }}</dd><small>genomic neighborhoods</small></div>
    <div><dt>CRISPR arrays</dt><dd :class="{ 'result-value': !includeCrisprArrays }">{{ includeCrisprArrays ? readableNumber(overview.crispr_array_count) : 'Not requested' }}</dd><small>{{ includeCrisprArrays ? 'CRISPRidentify' : 'optional detector disabled' }}</small></div>
    <div><dt>Nucleotide sequence</dt><dd>{{ readableBases(overview.total_bases) }}</dd><small>{{ readableNumber(overview.contig_count) }} contig{{ Number(overview.contig_count) === 1 ? '' : 's' }}</small></div>
    <div><dt>CasAndra time</dt><dd>{{ formatDuration(overview.wall_seconds) }}</dd><small>{{ readableNumber(overview.gene_count) }} genes inspected</small></div>
  </dl>
</template>

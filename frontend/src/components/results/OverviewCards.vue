<script setup>
import { readableBases } from "../../fasta.js";
import { formatDuration, readableNumber } from "../../utils/formatting.js";

defineProps({ overview: { type: Object, required: true } });
</script>

<template>
  <dl class="overview-cards">
    <div><dt>Cas proteins</dt><dd>{{ readableNumber(overview.cas_protein_count) }}</dd><small>sequence-model calls</small></div>
    <div><dt>Cas cassettes</dt><dd>{{ readableNumber(overview.cassette_count) }}</dd><small>genomic neighborhoods</small></div>
    <div><dt>CRISPR arrays</dt><dd>{{ readableNumber(overview.crispr_array_count) }}</dd><small>CRISPRidentify v2</small></div>
    <div><dt>Sequence</dt><dd>{{ readableBases(overview.total_bases) }}</dd><small>{{ readableNumber(overview.contig_count) }} contig{{ Number(overview.contig_count) === 1 ? '' : 's' }}</small></div>
    <div><dt>CasAndra time</dt><dd>{{ formatDuration(overview.wall_seconds) }}</dd><small>{{ readableNumber(overview.gene_count) }} genes inspected</small></div>
  </dl>
</template>

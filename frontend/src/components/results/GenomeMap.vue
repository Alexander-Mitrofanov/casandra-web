<script setup>
import { computed, ref, watch } from "vue";

import { readableBases } from "../../fasta.js";
import { contigsWithFeatures, featuresForContig, sourceForwardInterval } from "../../utils/results.js";

const props = defineProps({ summary: { type: Object, required: true } });
const contigs = computed(() => contigsWithFeatures(props.summary));
const selectedId = ref(contigs.value[0]?.id || "");

watch(contigs, (next) => {
  if (!next.some((item) => item.id === selectedId.value)) selectedId.value = next[0]?.id || "";
});

const selected = computed(() => contigs.value.find((item) => item.id === selectedId.value) || contigs.value[0] || { id: "", length: 1 });
const features = computed(() => featuresForContig(props.summary, selected.value.id));
const plot = Object.freeze({ x: 64, width: 872 });

function interval(row) {
  return sourceForwardInterval(row, selected.value.length);
}

function xFor(position) {
  const length = Math.max(1, Number(selected.value.length) || 1);
  return plot.x + ((Math.max(1, Number(position) || 1) - 1) / length) * plot.width;
}

function shape(row, y) {
  const { start, end } = interval(row);
  const exactStart = xFor(start);
  const exactEnd = xFor(end + 1);
  const x1 = Math.min(exactStart, exactEnd);
  const x2 = Math.max(x1 + 8, exactEnd);
  const head = Math.min(9, (x2 - x1) * 0.45);
  if (row.strand === "-") {
    return `${x1},${y + 8} ${x1 + head},${y} ${x2},${y} ${x2},${y + 16} ${x1 + head},${y + 16}`;
  }
  return `${x1},${y} ${x2 - head},${y} ${x2},${y + 8} ${x2 - head},${y + 16} ${x1},${y + 16}`;
}

const ticks = computed(() => {
  const length = Math.max(1, Number(selected.value.length) || 1);
  return [1, Math.round(length * 0.25), Math.round(length * 0.5), Math.round(length * 0.75), length]
    .filter((value, index, values) => values.indexOf(value) === index);
});
</script>

<template>
  <section class="result-section genome-map" aria-labelledby="genome-map-heading">
    <div class="result-heading"><div><p class="eyebrow">Coordinate explorer</p><h3 id="genome-map-heading">Source-forward feature map</h3></div><p>Left is base 1 in the submitted record. Arrowheads encode gene strand; the contig is never reverse-complemented for display.</p></div>
    <div v-if="contigs.length" class="contig-picker"><label for="contig-select">Contig</label><select id="contig-select" v-model="selectedId"><option v-for="contig in contigs" :key="contig.id" :value="contig.id">{{ contig.id }} · {{ readableBases(contig.length) }}</option></select><span>{{ features.cassettes.length }} cassette{{ features.cassettes.length === 1 ? '' : 's' }} · {{ features.casProteins.length }} Cas gene{{ features.casProteins.length === 1 ? '' : 's' }} · {{ features.crisprArrays.length }} array{{ features.crisprArrays.length === 1 ? '' : 's' }}</span></div>
    <div v-if="contigs.length" class="map-scroll" tabindex="0" aria-label="Scrollable genomic feature plot">
      <svg viewBox="0 0 1000 278" role="img" :aria-labelledby="`map-title map-description`">
        <title id="map-title">Cas and CRISPR features on {{ selected.id }}</title>
        <desc id="map-description">A source-forward map from coordinate 1 to {{ selected.length }} with separate tracks for Cas cassettes, Cas genes, and CRISPR arrays. Exact coordinates follow in tables.</desc>
        <defs><pattern id="array-stripes" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="5" height="8" fill="#a873e7"/><rect x="5" width="3" height="8" fill="#e9ddfb"/></pattern></defs>
        <text x="15" y="65" class="track-label">Cassette</text><text x="15" y="132" class="track-label">Cas gene</text><text x="15" y="199" class="track-label">CRISPR</text>
        <line :x1="plot.x" :x2="plot.x + plot.width" y1="68" y2="68" class="track-line"/><line :x1="plot.x" :x2="plot.x + plot.width" y1="135" y2="135" class="track-line"/><line :x1="plot.x" :x2="plot.x + plot.width" y1="202" y2="202" class="track-line"/>
        <g v-for="row in features.cassettes" :key="row.cassette_id"><rect :x="xFor(interval(row).start)" y="51" :width="Math.max(8, xFor(interval(row).end + 1) - xFor(interval(row).start))" height="28" rx="5" class="cassette-feature"><title>{{ row.cassette_id }}: {{ row.start }}–{{ row.end }}, {{ row.subtype || row.type || 'unresolved type' }}</title></rect></g>
        <g v-for="row in features.casProteins" :key="row.protein_id"><polygon :points="shape(row, 127)" class="gene-feature"><title>{{ row.protein_id }}: {{ row.start }}–{{ row.end }} ({{ row.strand }}), {{ row.profile || row.subtype || row.type || 'Cas' }}</title></polygon></g>
        <g v-for="row in features.crisprArrays" :key="row.array_id"><rect :x="xFor(interval(row).start)" y="190" :width="Math.max(7, xFor(interval(row).end + 1) - xFor(interval(row).start))" height="24" rx="3" fill="url(#array-stripes)" stroke="#7140aa"><title>{{ row.array_id }}: {{ row.start }}–{{ row.end }} ({{ row.strand || '?' }}), {{ row.category || 'unclassified' }}</title></rect></g>
        <line :x1="plot.x" :x2="plot.x + plot.width" y1="242" y2="242" class="axis-line"/>
        <g v-for="tick in ticks" :key="tick"><line :x1="xFor(tick)" :x2="xFor(tick)" y1="238" y2="248" class="axis-line"/><text :x="xFor(tick)" y="265" text-anchor="middle" class="tick-label">{{ tick.toLocaleString() }}</text></g>
        <text :x="plot.x" y="229" class="axis-end">5′ / base 1</text><text :x="plot.x + plot.width" y="229" text-anchor="end" class="axis-end">source 3′</text>
      </svg>
    </div>
    <div v-else class="empty-result">No contig coordinates were reported.</div>
    <div class="map-legend" aria-label="Map legend"><span><i class="legend-cassette"/>Cas cassette</span><span><i class="legend-gene"/>Cas protein; arrow = strand</span><span><i class="legend-array"/>CRISPR array</span></div>
  </section>
</template>

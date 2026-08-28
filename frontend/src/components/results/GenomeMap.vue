<script setup>
import { computed, ref, useId, watch } from "vue";

import { readableBases } from "../../fasta.js";
import { contigsWithFeatures, featuresForContig, sourceForwardInterval } from "../../utils/results.js";
import FeatureInspector from "./FeatureInspector.vue";

const props = defineProps({
  summary: { type: Object, required: true },
  showCrisprArrays: { type: Boolean, default: true },
  details: { type: Object, default: null },
  detailsLoading: Boolean,
  detailsError: { type: String, default: "" },
});
const emit = defineEmits(["details-needed", "feature-selected"]);

const instanceId = useId().replace(/[^A-Za-z0-9_-]/g, "");
const headingId = `${instanceId}-genome-map-heading`;
const contigSelectId = `${instanceId}-contig-select`;
const mapTitleId = `${instanceId}-map-title`;
const mapDescriptionId = `${instanceId}-map-description`;
const arrayPatternId = `${instanceId}-array-stripes`;

const detailedSources = computed(() => {
  if (!Array.isArray(props.details?.sources)) return [];
  return props.details.sources
    .filter((source) => source?.id && Number.isFinite(Number(source.length)))
    .map((source) => ({ ...source, id: String(source.id), length: Number(source.length) }));
});
const hasDetailedFeatures = computed(() => Array.isArray(props.details?.features));
const contigs = computed(() => detailedSources.value.length
  ? detailedSources.value
  : contigsWithFeatures(props.summary));
const selectedId = ref(contigs.value[0]?.id || "");
const selectedFeatureKey = ref("");

watch(contigs, (next) => {
  if (!next.some((item) => item.id === selectedId.value)) selectedId.value = next[0]?.id || "";
});
watch(selectedId, () => {
  if (!selectedFeatureKey.value) return;
  selectedFeatureKey.value = "";
  emit("feature-selected", null);
});

const selected = computed(() => contigs.value.find((item) => item.id === selectedId.value) || contigs.value[0] || { id: "", length: 1 });
const features = computed(() => {
  if (!hasDetailedFeatures.value) return featuresForContig(props.summary, selected.value.id);
  const rows = props.details.features.filter((row) => row?.contig_id === selected.value.id);
  return {
    cassettes: rows.filter((row) => row?.kind === "cassette"),
    casProteins: rows.filter((row) => row?.kind === "cas_gene"),
    crisprArrays: rows.filter((row) => row?.kind === "crispr_array"),
  };
});
const plot = Object.freeze({ x: 64, width: 872 });

function featureId(row, kind) {
  if (row?.feature_id) return String(row.feature_id);
  if (kind === "cas_gene") return String(row?.protein_id || "unknown-cas-gene");
  if (kind === "crispr_array") return String(row?.array_id || "unknown-array");
  return String(row?.cassette_id || "unknown-cassette");
}

function featureKey(row, kind) {
  return [kind, row?.contig_id || selected.value.id, featureId(row, kind)].join("\u0000");
}

function normalizeFeature(row, kind) {
  return {
    ...row,
    kind,
    feature_id: featureId(row, kind),
    sequences: Array.isArray(row?.sequences) ? row.sequences : [],
  };
}

const currentFeatureRows = computed(() => [
  ...features.value.cassettes.map((row) => [row, "cassette"]),
  ...features.value.casProteins.map((row) => [row, "cas_gene"]),
  ...(props.showCrisprArrays
    ? features.value.crisprArrays.map((row) => [row, "crispr_array"])
    : []),
]);
const selectedFeature = computed(() => {
  const match = currentFeatureRows.value.find(([row, kind]) => featureKey(row, kind) === selectedFeatureKey.value);
  return match ? normalizeFeature(match[0], match[1]) : null;
});

watch(currentFeatureRows, (next) => {
  if (selectedFeatureKey.value && next.some(([row, kind]) => featureKey(row, kind) === selectedFeatureKey.value)) return;
  const preferred = next.find(([, kind]) => kind === "cas_gene")
    || next.find(([, kind]) => kind === "cassette")
    || next.find(([, kind]) => kind === "crispr_array")
    || null;
  selectedFeatureKey.value = preferred ? featureKey(preferred[0], preferred[1]) : "";
  emit("feature-selected", preferred ? normalizeFeature(preferred[0], preferred[1]) : null);
}, { immediate: true });

function isSelected(row, kind) {
  return featureKey(row, kind) === selectedFeatureKey.value;
}

function selectFeature(row, kind) {
  const normalized = normalizeFeature(row, kind);
  selectedFeatureKey.value = featureKey(row, kind);
  emit("feature-selected", normalized);
  if (!hasDetailedFeatures.value && !props.detailsLoading) {
    emit("details-needed", {
      featureId: normalized.feature_id,
      featureKind: kind,
      contigId: normalized.contig_id || selected.value.id,
    });
  }
}

function featureLabel(row, kind) {
  const start = Number(row?.start);
  const end = Number(row?.end);
  const coordinates = Number.isFinite(start) && Number.isFinite(end)
    ? `${start.toLocaleString()} to ${end.toLocaleString()}`
    : "coordinates unavailable";
  const contig = row?.contig_id || selected.value.id;
  if (kind === "cas_gene") {
    const result = row?.result || row?.cas_family || row?.profile || row?.subtype || row?.type || "Cas";
    const strand = row?.strand === "-" ? "minus strand" : row?.strand === "+" ? "plus strand" : "strand unknown";
    return `${featureId(row, kind)}, Cas gene ${result}, ${coordinates} on ${contig}, ${strand}`;
  }
  if (kind === "crispr_array") {
    return `${featureId(row, kind)}, CRISPR array, ${coordinates} on ${contig}, ${row?.category || "unclassified"}`;
  }
  return `${featureId(row, kind)}, Cas cassette, ${coordinates} on ${contig}, ${row?.subtype || row?.type || "unresolved type"}`;
}

function typeClass(row) {
  const label = String(row?.type || row?.subtype || "").toUpperCase();
  const type = label.match(/^([IVX]+)/)?.[1] || "unknown";
  return `cas-type-${type.toLowerCase()}`;
}

function directLabel(row) {
  return String(row?.profile || row?.cas_family || row?.result || row?.subtype || row?.type || "Cas").slice(0, 14);
}

function interval(row) {
  return sourceForwardInterval(row, selected.value.length);
}

function xFor(position) {
  const length = Math.max(1, Number(selected.value.length) || 1);
  return plot.x + ((Math.max(1, Number(position) || 1) - 1) / length) * plot.width;
}

function pixelInterval(row) {
  const { start, end } = interval(row);
  const x1 = xFor(start);
  const x2 = xFor(end + 1);
  return { x: Math.min(x1, x2), width: Math.max(1, Math.abs(x2 - x1)) };
}

function hitBox(row, minimum = 58) {
  const exact = pixelInterval(row);
  const width = Math.min(plot.width, Math.max(minimum, exact.width));
  const center = exact.x + exact.width / 2;
  const x = Math.max(plot.x, Math.min(plot.x + plot.width - width, center - width / 2));
  return { x, width };
}

function shape(row, y) {
  const exact = pixelInterval(row);
  const x1 = exact.x;
  const x2 = exact.x + exact.width;
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
  <section id="result-explorer" class="result-section genome-map" :aria-labelledby="headingId">
    <div class="result-heading"><div><p class="eyebrow">Coordinate explorer</p><h3 :id="headingId">Source-forward feature map</h3></div><p>Left is base 1 in the submitted record. Select a feature once to see its contents; a CRISPR array shows every spacer together.</p></div>
    <div v-if="contigs.length" class="contig-picker"><label :for="contigSelectId">Contig</label><select :id="contigSelectId" v-model="selectedId"><option v-for="contig in contigs" :key="contig.id" :value="contig.id">{{ contig.id }} · {{ readableBases(contig.length) }}</option></select><span>{{ features.cassettes.length }} cassette{{ features.cassettes.length === 1 ? '' : 's' }} · {{ features.casProteins.length }} Cas gene{{ features.casProteins.length === 1 ? '' : 's' }}<template v-if="showCrisprArrays"> · {{ features.crisprArrays.length }} array{{ features.crisprArrays.length === 1 ? '' : 's' }}</template></span></div>
    <div v-if="contigs.length" class="map-scroll" tabindex="0" aria-label="Scrollable genomic feature plot">
      <span class="sr-only" role="img" :aria-label="`Cas${showCrisprArrays ? ' and CRISPR' : ''} features on ${selected.id}`">Interactive source-forward genomic feature map</span>
      <svg viewBox="0 0 1000 278" role="group" :aria-labelledby="`${mapTitleId} ${mapDescriptionId}`">
        <title :id="mapTitleId">Cas{{ showCrisprArrays ? ' and CRISPR' : '' }} features on {{ selected.id }}</title>
        <desc :id="mapDescriptionId">A source-forward map from coordinate 1 to {{ selected.length }} with separate tracks for Cas cassettes and Cas genes<template v-if="showCrisprArrays">, plus CRISPR arrays</template>. Every feature can be selected for exact annotation and available sequence details.</desc>
        <defs><pattern :id="arrayPatternId" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="5" height="8" fill="var(--crispr-repeat)"/><rect x="5" width="3" height="8" fill="var(--crispr-spacer)"/></pattern></defs>
        <text x="15" y="65" class="track-label">Cassette</text><text x="15" y="132" class="track-label">Cas gene</text><text v-if="showCrisprArrays" x="15" y="199" class="track-label">CRISPR</text>
        <line :x1="plot.x" :x2="plot.x + plot.width" y1="68" y2="68" class="track-line"/><line :x1="plot.x" :x2="plot.x + plot.width" y1="135" y2="135" class="track-line"/><line v-if="showCrisprArrays" :x1="plot.x" :x2="plot.x + plot.width" y1="202" y2="202" class="track-line"/>
        <g v-for="row in features.cassettes" :key="featureKey(row, 'cassette')" :class="['map-feature', 'map-feature-cassette', typeClass(row), { selected: isSelected(row, 'cassette') }]" role="button" tabindex="0" focusable="true" :aria-label="featureLabel(row, 'cassette')" :aria-pressed="isSelected(row, 'cassette')" data-feature-kind="cassette" @click="selectFeature(row, 'cassette')" @keydown.enter.prevent="selectFeature(row, 'cassette')" @keydown.space.prevent="selectFeature(row, 'cassette')"><rect :x="hitBox(row).x" y="36" :width="hitBox(row).width" height="58" fill="transparent" pointer-events="all" class="feature-hit"/><rect :x="pixelInterval(row).x" y="51" :width="pixelInterval(row).width" height="28" rx="4" class="cassette-feature"><title>{{ featureLabel(row, 'cassette') }}</title></rect><text v-if="pixelInterval(row).width >= 38" :x="pixelInterval(row).x + pixelInterval(row).width / 2" y="69" text-anchor="middle" class="feature-direct-label">{{ directLabel(row) }}</text></g>
        <g v-for="row in features.casProteins" :key="featureKey(row, 'cas_gene')" :class="['map-feature', 'map-feature-gene', typeClass(row), { selected: isSelected(row, 'cas_gene') }]" role="button" tabindex="0" focusable="true" :aria-label="featureLabel(row, 'cas_gene')" :aria-pressed="isSelected(row, 'cas_gene')" data-feature-kind="cas_gene" @click="selectFeature(row, 'cas_gene')" @keydown.enter.prevent="selectFeature(row, 'cas_gene')" @keydown.space.prevent="selectFeature(row, 'cas_gene')"><rect :x="hitBox(row).x" y="106" :width="hitBox(row).width" height="58" fill="transparent" pointer-events="all" class="feature-hit"/><polygon :points="shape(row, 127)" class="gene-feature"><title>{{ featureLabel(row, 'cas_gene') }}</title></polygon><text v-if="pixelInterval(row).width >= 38" :x="pixelInterval(row).x + pixelInterval(row).width / 2" y="139" text-anchor="middle" class="feature-direct-label">{{ directLabel(row) }}</text></g>
        <g v-if="showCrisprArrays"><g v-for="row in features.crisprArrays" :key="featureKey(row, 'crispr_array')" :class="['map-feature', 'map-feature-array', { selected: isSelected(row, 'crispr_array') }]" role="button" tabindex="0" focusable="true" :aria-label="featureLabel(row, 'crispr_array')" :aria-pressed="isSelected(row, 'crispr_array')" data-feature-kind="crispr_array" @click="selectFeature(row, 'crispr_array')" @keydown.enter.prevent="selectFeature(row, 'crispr_array')" @keydown.space.prevent="selectFeature(row, 'crispr_array')"><rect :x="hitBox(row).x" y="173" :width="hitBox(row).width" height="58" fill="transparent" pointer-events="all" class="feature-hit"/><rect :x="pixelInterval(row).x" y="190" :width="pixelInterval(row).width" height="24" rx="3" :fill="`url(#${arrayPatternId})`" stroke="var(--purple)" class="array-feature"><title>{{ featureLabel(row, 'crispr_array') }}</title></rect></g></g>
        <line :x1="plot.x" :x2="plot.x + plot.width" y1="242" y2="242" class="axis-line"/>
        <g v-for="tick in ticks" :key="tick"><line :x1="xFor(tick)" :x2="xFor(tick)" y1="238" y2="248" class="axis-line"/><text :x="xFor(tick)" y="265" text-anchor="middle" class="tick-label">{{ tick.toLocaleString() }}</text></g>
        <text :x="plot.x" y="229" class="axis-end">5′ / base 1</text><text :x="plot.x + plot.width" y="229" text-anchor="end" class="axis-end">source 3′</text>
      </svg>
    </div>
    <div v-else class="empty-result">No contig coordinates were reported.</div>
    <div class="map-legend" aria-label="Map legend"><span><i class="legend-cassette"/>Cas cassette</span><span><i class="legend-gene"/>Cas protein; arrow = strand</span><span v-if="showCrisprArrays"><i class="legend-array"/>CRISPR array</span></div>
    <FeatureInspector :feature="selectedFeature" :loading="detailsLoading" :error="detailsError"/>
  </section>
</template>

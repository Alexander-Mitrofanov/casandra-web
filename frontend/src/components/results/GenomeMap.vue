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
const mapSvg = ref(null);

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
const fullLength = computed(() => Math.max(1, Number(selected.value.length) || 1));
const viewStart = ref(0);
const viewEnd = ref(fullLength.value);
const viewSpan = computed(() => Math.max(1, viewEnd.value - viewStart.value));
const isFullView = computed(() => (
  Math.abs(viewStart.value) < 0.5
  && Math.abs(viewEnd.value - fullLength.value) < 0.5
));
const zoomLevel = computed(() => fullLength.value / viewSpan.value);
const visibleStart = computed(() => Math.max(1, Math.floor(viewStart.value) + 1));
const visibleEnd = computed(() => Math.min(fullLength.value, Math.ceil(viewEnd.value)));
const zoomStatus = computed(() => isFullView.value
  ? `Full view · bases 1–${fullLength.value.toLocaleString()}`
  : `${zoomLevel.value < 10 ? zoomLevel.value.toFixed(1) : Math.round(zoomLevel.value)}× · bases ${visibleStart.value.toLocaleString()}–${visibleEnd.value.toLocaleString()}`);

function resetView() {
  viewStart.value = 0;
  viewEnd.value = fullLength.value;
}

watch(() => [selected.value.id, fullLength.value], resetView, { immediate: true });

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
  revealFeature(row);
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

function xForBoundary(boundary) {
  const coordinate = Math.max(viewStart.value, Math.min(viewEnd.value, Number(boundary) || 0));
  return plot.x + ((coordinate - viewStart.value) / viewSpan.value) * plot.width;
}

function xFor(position) {
  return xForBoundary(Math.max(0, (Number(position) || 1) - 1));
}

function pixelInterval(row) {
  const { start, end } = interval(row);
  const x1 = xForBoundary(Math.max(start - 1, viewStart.value));
  const x2 = xForBoundary(Math.min(end, viewEnd.value));
  return { x: Math.min(x1, x2), width: Math.max(1, Math.abs(x2 - x1)) };
}

function isVisible(row) {
  const { start, end } = interval(row);
  return end > viewStart.value && start - 1 < viewEnd.value;
}

function revealFeature(row) {
  const { start, end } = interval(row);
  const featureStart = start - 1;
  const featureEnd = end;
  if (featureStart >= viewStart.value && featureEnd <= viewEnd.value) return;
  const featureSpan = Math.max(1, featureEnd - featureStart);
  const nextSpan = Math.min(fullLength.value, Math.max(viewSpan.value, featureSpan * 1.2));
  const latestStart = Math.max(0, fullLength.value - nextSpan);
  const nextStart = Math.max(0, Math.min(latestStart, (featureStart + featureEnd - nextSpan) / 2));
  viewStart.value = nextStart;
  viewEnd.value = nextStart + nextSpan;
}

function trackLayout(rows, kind, minimum = 58) {
  const plotEnd = plot.x + plot.width;
  const items = rows.map((row) => {
    const exact = pixelInterval(row);
    const exactEnd = exact.x + exact.width;
    const center = exact.x + exact.width / 2;
    const desiredWidth = Math.min(plot.width, Math.max(minimum, exact.width));
    const desiredX = Math.max(plot.x, Math.min(plotEnd - desiredWidth, center - desiredWidth / 2));
    return {
      row,
      key: featureKey(row, kind),
      exact,
      exactEnd,
      center,
      desiredX,
      desiredEnd: desiredX + desiredWidth,
    };
  }).sort((left, right) => (
    left.center - right.center
    || left.exact.x - right.exact.x
    || left.key.localeCompare(right.key)
  ));

  const boundaries = items.slice(0, -1).map((left, index) => {
    const right = items[index + 1];
    const overlapStart = Math.max(left.exact.x, right.exact.x);
    const overlapEnd = Math.min(left.exactEnd, right.exactEnd);
    if (overlapStart <= overlapEnd) return (overlapStart + overlapEnd) / 2;
    return (left.exactEnd + right.exact.x) / 2;
  });

  return items.map((item, index) => {
    const ownedStart = index ? boundaries[index - 1] : plot.x;
    const ownedEnd = index < boundaries.length ? boundaries[index] : plotEnd;
    const x = Math.max(item.desiredX, ownedStart);
    const end = Math.min(item.desiredEnd, ownedEnd);
    return { ...item, hit: { x, width: Math.max(0, end - x) } };
  });
}

const cassetteLayout = computed(() => trackLayout(features.value.cassettes.filter(isVisible), "cassette"));
const geneLayout = computed(() => trackLayout(features.value.casProteins.filter(isVisible), "cas_gene"));
const arrayLayout = computed(() => trackLayout(features.value.crisprArrays.filter(isVisible), "crispr_array"));

function featureChoices(rows, kind) {
  return rows.map((row) => ({ row, key: featureKey(row, kind) })).sort((left, right) => {
    const leftInterval = interval(left.row);
    const rightInterval = interval(right.row);
    return leftInterval.start - rightInterval.start
      || leftInterval.end - rightInterval.end
      || left.key.localeCompare(right.key);
  });
}

const cassetteChoices = computed(() => featureChoices(features.value.cassettes, "cassette"));
const geneChoices = computed(() => featureChoices(features.value.casProteins, "cas_gene"));

function geneName(row) {
  return String(row?.result || row?.cas_family || row?.profile || row?.subtype || row?.type || "Cas");
}

function cassetteName(row) {
  return String(row?.subtype || row?.type || "Unresolved");
}

function coordinateLabel(row) {
  const { start, end } = interval(row);
  return `${start.toLocaleString()}\u2013${end.toLocaleString()}`;
}

function shape(row, y) {
  const exact = pixelInterval(row);
  const x1 = exact.x;
  const x2 = exact.x + exact.width;
  const head = Math.min(9, (x2 - x1) * 0.45);
  const source = interval(row);
  if ((row.strand === "-" && source.start - 1 < viewStart.value) || (row.strand !== "-" && source.end > viewEnd.value)) {
    return `${x1},${y} ${x2},${y} ${x2},${y + 16} ${x1},${y + 16}`;
  }
  if (row.strand === "-") {
    return `${x1},${y + 8} ${x1 + head},${y} ${x2},${y} ${x2},${y + 16} ${x1 + head},${y + 16}`;
  }
  return `${x1},${y} ${x2 - head},${y} ${x2},${y + 8} ${x2 - head},${y + 16} ${x1},${y + 16}`;
}

const ticks = computed(() => {
  const start = visibleStart.value;
  const end = visibleEnd.value;
  const span = Math.max(0, end - start);
  return [start, Math.round(start + span * 0.25), Math.round(start + span * 0.5), Math.round(start + span * 0.75), end]
    .filter((value, index, values) => values.indexOf(value) === index);
});

function handleWheel(event) {
  if (!event.shiftKey || event.ctrlKey || event.metaKey) return;
  const delta = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX;
  if (!delta) return;
  event.preventDefault();

  const minimumSpan = Math.min(fullLength.value, 200);
  const deltaPixels = delta * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 500 : 1);
  const factor = Math.exp(Math.max(-240, Math.min(240, deltaPixels)) * 0.003);
  const nextSpan = Math.max(minimumSpan, Math.min(fullLength.value, viewSpan.value * factor));
  if (Math.abs(nextSpan - viewSpan.value) < 0.5) return;

  const bounds = mapSvg.value?.getBoundingClientRect();
  const pointerX = bounds?.width > 0
    ? ((event.clientX - bounds.left) / bounds.width) * 1000
    : plot.x + plot.width / 2;
  const ratio = Math.max(0, Math.min(1, (pointerX - plot.x) / plot.width));
  if (nextSpan >= fullLength.value - 0.5) {
    resetView();
    return;
  }
  const focus = viewStart.value + ratio * viewSpan.value;
  const latestStart = Math.max(0, fullLength.value - nextSpan);
  const nextStart = Math.max(0, Math.min(latestStart, focus - ratio * nextSpan));
  viewStart.value = nextStart;
  viewEnd.value = nextStart + nextSpan;
}
</script>

<template>
  <section id="result-explorer" class="result-section genome-map" :aria-labelledby="headingId">
    <div class="result-heading"><div><p class="eyebrow">Coordinate explorer</p><h3 :id="headingId">Source-forward feature map</h3></div><p>Hold Shift and scroll over the map to zoom around the pointer. Scroll without Shift to move through the page. Select a feature to inspect it.</p></div>
    <div v-if="contigs.length" class="contig-picker"><label :for="contigSelectId">Contig</label><select :id="contigSelectId" v-model="selectedId"><option v-for="contig in contigs" :key="contig.id" :value="contig.id">{{ contig.id }} · {{ readableBases(contig.length) }}</option></select><span>{{ features.cassettes.length }} cassette{{ features.cassettes.length === 1 ? '' : 's' }} · {{ features.casProteins.length }} Cas gene{{ features.casProteins.length === 1 ? '' : 's' }}<template v-if="showCrisprArrays"> · {{ features.crisprArrays.length }} array{{ features.crisprArrays.length === 1 ? '' : 's' }}</template></span></div>
    <div v-if="contigs.length" class="map-scroll">
      <div class="map-toolbar"><button type="button" :disabled="isFullView" @click="resetView">Back to full view</button><output aria-label="Map zoom status">{{ zoomStatus }}</output></div>
      <div class="map-canvas" tabindex="0" aria-label="Genomic feature plot; hold Shift and scroll to zoom" :data-view-start="visibleStart" :data-view-end="visibleEnd" :data-zoom-level="zoomLevel.toFixed(3)" @wheel="handleWheel">
        <span class="sr-only" role="img" :aria-label="`Cas${showCrisprArrays ? ' and CRISPR' : ''} features on ${selected.id}`">Interactive source-forward genomic feature map</span>
        <svg ref="mapSvg" viewBox="0 0 1000 278" role="group" :aria-labelledby="`${mapTitleId} ${mapDescriptionId}`">
          <title :id="mapTitleId">Cas{{ showCrisprArrays ? ' and CRISPR' : '' }} features on {{ selected.id }}</title>
          <desc :id="mapDescriptionId">A source-forward map of bases {{ visibleStart }} to {{ visibleEnd }} with separate tracks for Cas cassettes and Cas genes<template v-if="showCrisprArrays">, plus CRISPR arrays</template>. Hold Shift and scroll to zoom in or out. Every feature can be selected for exact annotation and available sequence details.</desc>
          <defs><pattern :id="arrayPatternId" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="5" height="8" fill="var(--crispr-repeat)"/><rect x="5" width="3" height="8" fill="var(--crispr-spacer)"/></pattern></defs>
          <text x="15" y="65" class="track-label">Cassette</text><text x="15" y="132" class="track-label">Cas gene</text><text v-if="showCrisprArrays" x="15" y="199" class="track-label">CRISPR</text>
          <line :x1="plot.x" :x2="plot.x + plot.width" y1="68" y2="68" class="track-line"/><line :x1="plot.x" :x2="plot.x + plot.width" y1="135" y2="135" class="track-line"/><line v-if="showCrisprArrays" :x1="plot.x" :x2="plot.x + plot.width" y1="202" y2="202" class="track-line"/>
          <g v-for="item in cassetteLayout" :key="item.key" :class="['map-feature', 'map-feature-cassette', typeClass(item.row), { selected: isSelected(item.row, 'cassette') }]" role="button" tabindex="0" focusable="true" :aria-label="featureLabel(item.row, 'cassette')" :aria-pressed="isSelected(item.row, 'cassette')" data-feature-kind="cassette" :data-feature-id="featureId(item.row, 'cassette')" @click="selectFeature(item.row, 'cassette')" @keydown.enter.prevent="selectFeature(item.row, 'cassette')" @keydown.space.prevent="selectFeature(item.row, 'cassette')"><rect :x="item.hit.x" y="36" :width="item.hit.width" height="58" fill="transparent" pointer-events="all" class="feature-hit" data-feature-hit/><rect :x="item.exact.x" y="51" :width="item.exact.width" height="28" rx="4" class="cassette-feature"><title>{{ featureLabel(item.row, 'cassette') }}</title></rect><text v-if="item.exact.width >= 38" :x="item.exact.x + item.exact.width / 2" y="69" text-anchor="middle" class="feature-direct-label">{{ directLabel(item.row) }}</text></g>
          <g v-for="item in geneLayout" :key="item.key" :class="['map-feature', 'map-feature-gene', typeClass(item.row), { selected: isSelected(item.row, 'cas_gene') }]" role="button" tabindex="0" focusable="true" :aria-label="featureLabel(item.row, 'cas_gene')" :aria-pressed="isSelected(item.row, 'cas_gene')" data-feature-kind="cas_gene" :data-feature-id="featureId(item.row, 'cas_gene')" @click="selectFeature(item.row, 'cas_gene')" @keydown.enter.prevent="selectFeature(item.row, 'cas_gene')" @keydown.space.prevent="selectFeature(item.row, 'cas_gene')"><rect :x="item.hit.x" y="106" :width="item.hit.width" height="58" fill="transparent" pointer-events="all" class="feature-hit" data-feature-hit/><polygon :points="shape(item.row, 127)" class="gene-feature"><title>{{ featureLabel(item.row, 'cas_gene') }}</title></polygon><text v-if="item.exact.width >= 38" :x="item.exact.x + item.exact.width / 2" y="139" text-anchor="middle" class="feature-direct-label">{{ directLabel(item.row) }}</text></g>
          <g v-if="showCrisprArrays"><g v-for="item in arrayLayout" :key="item.key" :class="['map-feature', 'map-feature-array', { selected: isSelected(item.row, 'crispr_array') }]" role="button" tabindex="0" focusable="true" :aria-label="featureLabel(item.row, 'crispr_array')" :aria-pressed="isSelected(item.row, 'crispr_array')" data-feature-kind="crispr_array" :data-feature-id="featureId(item.row, 'crispr_array')" @click="selectFeature(item.row, 'crispr_array')" @keydown.enter.prevent="selectFeature(item.row, 'crispr_array')" @keydown.space.prevent="selectFeature(item.row, 'crispr_array')"><rect :x="item.hit.x" y="173" :width="item.hit.width" height="58" fill="transparent" pointer-events="all" class="feature-hit" data-feature-hit/><rect :x="item.exact.x" y="190" :width="item.exact.width" height="24" rx="3" :fill="`url(#${arrayPatternId})`" stroke="var(--purple)" class="array-feature"><title>{{ featureLabel(item.row, 'crispr_array') }}</title></rect></g></g>
          <line :x1="plot.x" :x2="plot.x + plot.width" y1="242" y2="242" class="axis-line"/>
          <g v-for="tick in ticks" :key="tick"><line :x1="xFor(tick)" :x2="xFor(tick)" y1="238" y2="248" class="axis-line"/><text :x="xFor(tick)" y="265" text-anchor="middle" class="tick-label">{{ tick.toLocaleString() }}</text></g>
          <text :x="plot.x" y="229" class="axis-end">base {{ visibleStart.toLocaleString() }}</text><text :x="plot.x + plot.width" y="229" text-anchor="end" class="axis-end">base {{ visibleEnd.toLocaleString() }}</text>
        </svg>
      </div>
    </div>
    <div v-else class="empty-result">No contig coordinates were reported.</div>
    <div v-if="contigs.length && cassetteChoices.length" class="feature-quick-select" role="group" :aria-label="`Cas cassettes on ${selected.id}`">
      <span class="feature-quick-select-label">Select cassette</span>
      <div class="feature-quick-select-buttons">
        <button v-for="item in cassetteChoices" :key="item.key" type="button" :class="{ selected: isSelected(item.row, 'cassette') }" :aria-label="`Select cassette ${cassetteName(item.row)}, bases ${coordinateLabel(item.row)}`" :aria-pressed="isSelected(item.row, 'cassette')" :data-quick-feature-id="featureId(item.row, 'cassette')" @click="selectFeature(item.row, 'cassette')"><strong>{{ cassetteName(item.row) }}</strong><span>{{ coordinateLabel(item.row) }}</span></button>
      </div>
    </div>
    <div v-if="contigs.length && geneChoices.length" class="feature-quick-select" role="group" :aria-label="`Cas genes on ${selected.id}`">
      <span class="feature-quick-select-label">Select Cas gene</span>
      <div class="feature-quick-select-buttons">
        <button v-for="item in geneChoices" :key="item.key" type="button" :class="{ selected: isSelected(item.row, 'cas_gene') }" :aria-label="`Select ${geneName(item.row)}, bases ${coordinateLabel(item.row)}`" :aria-pressed="isSelected(item.row, 'cas_gene')" :data-quick-feature-id="featureId(item.row, 'cas_gene')" @click="selectFeature(item.row, 'cas_gene')"><strong>{{ geneName(item.row) }}</strong><span>{{ coordinateLabel(item.row) }}</span></button>
      </div>
    </div>
    <div class="map-legend" aria-label="Map legend"><span><i class="legend-cassette"/>Cas cassette</span><span><i class="legend-gene"/>Cas protein; arrow = strand</span><span v-if="showCrisprArrays"><i class="legend-array"/>CRISPR array</span><span class="map-zoom-hint">Use Shift + scroll to zoom in/out</span></div>
    <FeatureInspector :feature="selectedFeature" :loading="detailsLoading" :error="detailsError"/>
  </section>
</template>

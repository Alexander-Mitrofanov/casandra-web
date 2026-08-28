<script setup>
import { computed, ref, watch } from "vue";

import { asArray } from "../../utils/formatting.js";
import FeatureInspector from "./FeatureInspector.vue";

const props = defineProps({
  summary: { type: Object, required: true },
  details: { type: Object, default: null },
  detailsLoading: Boolean,
  detailsError: { type: String, default: "" },
});
const emit = defineEmits(["details-needed"]);

const query = ref("");
const callFilter = ref("all");
const page = ref(1);
const selectedId = ref("");
// Fifteen marks keep each pointer slot at least 44 CSS px at the plot's 760 px minimum width.
const pageSize = 15;
const maximumPlotMagnitude = 1_000_000_000_000;
const analysisMode = computed(() => props.summary.analysis_mode || "annotate_cas_genes");
const detailedProteins = computed(() => asArray(props.details?.features).filter((feature) => feature?.kind === "protein"));
const summaryProteins = computed(() => asArray(props.summary.protein_predictions));

function featureKey(row) {
  return String(row?.feature_id || row?.protein_id || "");
}

function finiteNumber(value) {
  if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function plotNumber(value) {
  const number = finiteNumber(value);
  return number !== null && Math.abs(number) <= maximumPlotMagnitude ? number : null;
}

const proteins = computed(() => {
  const detailsById = new Map(detailedProteins.value.map((row) => [featureKey(row), row]));
  const merged = summaryProteins.value.map((row) => ({
    ...row,
    ...(detailsById.get(featureKey(row)) || {}),
  }));
  const known = new Set(merged.map(featureKey));
  for (const row of detailedProteins.value) {
    if (!known.has(featureKey(row))) merged.push(row);
  }
  return merged;
});
const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase();
  return proteins.value.filter((row) => {
    if (callFilter.value === "cas" && row?.is_cas !== true) return false;
    if (callFilter.value === "no_cas" && row?.is_cas !== false) return false;
    if (!needle) return true;
    return [row?.protein_id, row?.feature_id, row?.result, row?.profile, row?.type, row?.subtype]
      .some((value) => String(value || "").toLowerCase().includes(needle));
  });
});
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize)));
const visible = computed(() => filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize));
const selected = computed(() => proteins.value.find((row) => featureKey(row) === selectedId.value) || null);
const casCount = computed(() => proteins.value.filter((row) => row?.is_cas === true).length);
const casPercent = computed(() => proteins.value.length ? (casCount.value / proteins.value.length) * 100 : 0);
const cassette = computed(() => props.summary.cassette_classification || {});

watch([query, callFilter], () => { page.value = 1; });
watch(pageCount, (count) => { if (page.value > count) page.value = count; });
watch(proteins, (next) => {
  if (selectedId.value && next.some((row) => featureKey(row) === selectedId.value)) return;
  selectedId.value = featureKey(next[0]);
}, { immediate: true });
watch(visible, (next) => {
  if (selectedId.value && next.some((row) => featureKey(row) === selectedId.value)) return;
  selectedId.value = featureKey(next[0]);
}, { immediate: true });

function selectProtein(row) {
  const id = featureKey(row);
  if (!id) return;
  selectedId.value = id;
  if (!asArray(row?.sequences).length && !props.detailsLoading) {
    emit("details-needed", {
      featureId: id,
      proteinId: String(row?.protein_id || id),
      inputIndex: finiteNumber(row?.input_index),
    });
  }
}

function isSelected(row) {
  return featureKey(row) === selectedId.value;
}

function resultLabel(row) {
  if (row?.is_cas === false) return "no cas";
  return String(row?.result || row?.cas_family || row?.profile || "Cas");
}

function inputOrdinal(row) {
  const index = finiteNumber(row?.input_index);
  if (index !== null && Number.isInteger(index) && index >= 0) return index + 1;
  const fallback = proteins.value.indexOf(row);
  return fallback >= 0 ? fallback + 1 : 1;
}

function typeClass(row) {
  const label = String(row?.type || row?.subtype || "").toUpperCase();
  const type = label.match(/^([IVX]+)/)?.[1] || "unknown";
  return `cas-type-${type.toLowerCase()}`;
}

function blockWidth(row) {
  const value = finiteNumber(row?.residue_count);
  const residues = value !== null && value > 0 ? value : 0;
  return `${Math.max(72, Math.min(178, 62 + Math.sqrt(residues) * 5))}px`;
}

const margins = computed(() => visible.value.map((row) => plotNumber(row?.score_margin)).filter((value) => value !== null));
const thresholds = computed(() => visible.value.map((row) => plotNumber(row?.evidence?.decision_threshold)).filter((value) => value !== null));
const sharedThreshold = computed(() => thresholds.value.length && thresholds.value.every((value) => value === thresholds.value[0]) ? thresholds.value[0] : null);
const domain = computed(() => {
  const values = [...margins.value, ...(sharedThreshold.value === null ? [] : [sharedThreshold.value]), 0];
  const low = Math.min(...values);
  const high = Math.max(...values);
  const padding = Math.max(1, (high - low) * 0.12);
  return { low: low - padding, high: high + padding };
});
const plot = Object.freeze({ x: 78, y: 20, width: 872, height: 168, unavailableY: 213 });
function xFor(index) {
  return visible.value.length <= 1 ? plot.x + plot.width / 2 : plot.x + (index / (visible.value.length - 1)) * plot.width;
}
function slotBounds(index) {
  if (visible.value.length <= 1) return { x: plot.x, width: plot.width };
  const center = xFor(index);
  const left = index === 0 ? plot.x : (xFor(index - 1) + center) / 2;
  const right = index === visible.value.length - 1
    ? plot.x + plot.width
    : (center + xFor(index + 1)) / 2;
  return { x: left, width: Math.max(1, right - left) };
}
function yFor(value) {
  const number = plotNumber(value);
  if (number === null) return plot.unavailableY;
  return plot.y + ((domain.value.high - number) / (domain.value.high - domain.value.low || 1)) * plot.height;
}
const yTicks = computed(() => Array.from({ length: 5 }, (_, index) => domain.value.low + ((domain.value.high - domain.value.low) * index) / 4));
const unavailableScores = computed(() => visible.value.some((row) => plotNumber(row?.score_margin) === null));

function scoreMarginLabel(row) {
  const value = finiteNumber(row?.score_margin);
  if (value === null) return "score margin unavailable";
  if (plotNumber(value) === null) return `score margin ${String(value)}, outside the supported plot range`;
  return `score margin ${value.toFixed(3)}`;
}

function markAriaLabel(row) {
  return `${row?.protein_id || row?.feature_id || "Protein"}: ${resultLabel(row)}; ${scoreMarginLabel(row)}; submitted FASTA record ${inputOrdinal(row)}`;
}

function cassetteEvidenceLabel() {
  const value = finiteNumber(cassette.value?.confidence);
  return value === null ? "—" : value.toFixed(3);
}
</script>

<template>
  <section id="result-explorer" class="result-section protein-explorer" aria-labelledby="protein-explorer-heading">
    <div class="result-heading"><div><p class="eyebrow">Interactive result explorer</p><h3 id="protein-explorer-heading">{{ analysisMode === 'classify_cassette' ? 'Ordered cassette architecture' : 'Protein call landscape' }}</h3></div><p>{{ analysisMode === 'classify_cassette' ? 'Blocks preserve submitted FASTA order; widths reflect protein length and do not imply genomic coordinates.' : 'Marks show model score margin in submitted FASTA order. Scores are model evidence, not probabilities.' }}</p></div>

    <div v-if="analysisMode === 'annotate_cas_genes'" class="protein-composition" role="img" :aria-label="`Cas and no-cas composition: ${casCount} Cas, ${proteins.length - casCount} no cas, ${proteins.length} proteins total`"><span class="cas-segment" :style="{ width: `${casPercent}%` }"/><span class="no-cas-segment" :style="{ width: `${100 - casPercent}%` }"/><p><strong>{{ casCount.toLocaleString() }} Cas</strong><span>{{ (proteins.length - casCount).toLocaleString() }} no cas</span></p></div>

    <div class="protein-controls"><label>Find protein<input v-model="query" type="search" placeholder="ID, family, type…"></label><label>Calls<select v-model="callFilter"><option value="all">All calls</option><option value="cas">Cas only</option><option value="no_cas">no cas only</option></select></label><span>{{ filtered.length.toLocaleString() }} protein{{ filtered.length === 1 ? '' : 's' }}</span></div>

    <template v-if="analysisMode === 'annotate_cas_genes'">
      <div v-if="visible.length" class="protein-plot-scroll" role="region" tabindex="0" aria-label="Scrollable protein score plot"><svg viewBox="0 0 1000 252" role="group" aria-labelledby="protein-plot-title protein-plot-description"><title id="protein-plot-title">Protein model score margins</title><desc id="protein-plot-description">One selectable mark per visible protein in submitted order. Filled marks are Cas calls and hollow marks are no-cas calls. Marks on the unavailable lane have no usable score position.</desc><line :x1="plot.x" :x2="plot.x" :y1="plot.y" :y2="plot.y + plot.height" class="score-axis"/><line :x1="plot.x" :x2="plot.x + plot.width" :y1="plot.y + plot.height" :y2="plot.y + plot.height" class="score-axis"/><g v-for="tick in yTicks" :key="tick"><line :x1="plot.x" :x2="plot.x + plot.width" :y1="yFor(tick)" :y2="yFor(tick)" class="score-grid"/><text :x="plot.x - 10" :y="yFor(tick) + 4" text-anchor="end" class="score-tick">{{ tick.toFixed(1) }}</text></g><g v-if="sharedThreshold !== null"><line :x1="plot.x" :x2="plot.x + plot.width" :y1="yFor(sharedThreshold)" :y2="yFor(sharedThreshold)" class="threshold-line"/><text :x="plot.x + plot.width" :y="yFor(sharedThreshold) - 7" text-anchor="end" class="threshold-label">decision threshold {{ sharedThreshold.toFixed(1) }}</text></g><g v-if="unavailableScores" class="score-unavailable-lane"><line :x1="plot.x" :x2="plot.x + plot.width" :y1="plot.unavailableY" :y2="plot.unavailableY" class="score-grid"/><text :x="plot.x - 10" :y="plot.unavailableY + 4" text-anchor="end" class="score-tick">N/A</text></g><g v-for="(row, index) in visible" :key="featureKey(row)" :class="['protein-score-mark', typeClass(row), { selected: isSelected(row), 'no-cas': row.is_cas === false, 'score-unavailable': plotNumber(row.score_margin) === null }]" role="button" tabindex="0" focusable="true" :aria-pressed="isSelected(row)" :aria-label="markAriaLabel(row)" @click="selectProtein(row)" @keydown.enter.prevent="selectProtein(row)" @keydown.space.prevent="selectProtein(row)"><title>{{ markAriaLabel(row) }}</title><rect :x="slotBounds(index).x" :y="plot.y - 8" :width="slotBounds(index).width" :height="plot.unavailableY - plot.y + 16" class="score-hit"/><circle :cx="xFor(index)" :cy="yFor(row.score_margin)" r="5.5" class="score-dot" pointer-events="none"/></g><text x="18" y="112" transform="rotate(-90 18 112)" text-anchor="middle" class="score-axis-title">Model score margin</text><text x="514" y="244" text-anchor="middle" class="score-axis-title">Filtered proteins in submitted FASTA order</text></svg></div>
      <div v-else class="empty-result">No proteins match the current view.</div>
    </template>

    <template v-else>
      <div class="cassette-classification-banner"><span>Classification</span><strong>{{ cassette.result || cassette.subtype || cassette.type || 'unclassified' }}</strong><small>{{ cassette.method || 'method not reported' }} · model evidence {{ cassetteEvidenceLabel() }}</small></div>
      <ol v-if="visible.length" class="cassette-strip" aria-label="Ordered submitted proteins"><li v-for="row in visible" :key="featureKey(row)" class="cassette-protein-item" :style="{ '--block-width': blockWidth(row) }"><button type="button" :class="['cassette-protein-block', typeClass(row), { selected: isSelected(row), 'no-cas': row.is_cas === false }]" :aria-pressed="isSelected(row)" :aria-label="`${row.protein_id || row.feature_id}: ${resultLabel(row)}; submitted FASTA record ${inputOrdinal(row)}`" @click="selectProtein(row)" @keydown.enter.prevent="selectProtein(row)" @keydown.space.prevent="selectProtein(row)"><small>#{{ inputOrdinal(row) }}</small><strong>{{ row.protein_id || row.feature_id }}</strong><span>{{ resultLabel(row) }}</span></button></li></ol>
      <div v-else class="empty-result">No proteins match the current view.</div>
      <p class="coordinate-free-note">FASTA record order → · coordinate-free protein set</p>
    </template>

    <div v-if="pageCount > 1" class="result-pagination" aria-label="Protein result pages"><button type="button" :disabled="page === 1" aria-label="Previous protein results page" @click="page -= 1">Previous</button><span aria-live="polite">Page {{ page.toLocaleString() }} of {{ pageCount.toLocaleString() }}</span><button type="button" :disabled="page === pageCount" aria-label="Next protein results page" @click="page += 1">Next</button></div>
    <FeatureInspector :feature="selected" :loading="detailsLoading" :error="detailsError"/>
  </section>
</template>

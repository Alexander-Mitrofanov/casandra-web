<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";

import { saveBlob } from "../../utils/download.js";
import { downloadName, evidenceScore } from "../../utils/formatting.js";
import AppIcon from "../common/AppIcon.vue";

const props = defineProps({
  feature: { type: Object, default: null },
  loading: Boolean,
  error: { type: String, default: "" },
});

const copied = ref("");
const copyError = ref("");
const copyAnnouncement = ref("");
let copyTimer;

function finiteNumber(value) {
  if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatEvidence(value) {
  const number = finiteNumber(value);
  return number === null ? null : evidenceScore(number, false);
}

function formatEvalue(value) {
  const number = finiteNumber(value);
  if (number === null) return null;
  if (number === 0) return "0";
  return Math.abs(number) < 0.001 || Math.abs(number) >= 1_000_000
    ? number.toExponential(3)
    : number.toFixed(3);
}

const sequences = computed(() => (Array.isArray(props.feature?.sequences) ? props.feature.sequences : [])
  .map((sequence, index) => {
    if (!sequence || typeof sequence !== "object") return null;
    const molecule = sequence.molecule === "protein" || sequence.molecule === "dna" ? sequence.molecule : null;
    const value = typeof sequence.sequence === "string" ? sequence.sequence.replace(/\s+/g, "") : "";
    if (!molecule || !value) return null;
    const reportedLength = finiteNumber(sequence.length);
    return {
      ...sequence,
      key: String(sequence.key || `${molecule}_${index + 1}`),
      domKey: `${String(sequence.key || molecule)}-${index}`,
      label: String(sequence.label || (molecule === "protein" ? "Protein" : "DNA")),
      molecule,
      orientation: String(sequence.orientation || "orientation_not_reported"),
      length: reportedLength !== null && reportedLength >= 0
        ? reportedLength
        : (molecule === "protein" ? value.replace(/\*$/, "").length : value.length),
      sha256: typeof sequence.sha256 === "string" ? sequence.sha256 : "",
      sequence: value,
    };
  })
  .filter(Boolean));
const featureKind = computed(() => String(props.feature?.kind || "feature"));
const featureId = computed(() => String(props.feature?.feature_id || props.feature?.protein_id || props.feature?.array_id || props.feature?.cassette_id || "Selected feature"));
const result = computed(() => {
  if (props.feature?.is_cas === false) return "no cas";
  return props.feature?.result || props.feature?.cas_family || props.feature?.profile || props.feature?.subtype || props.feature?.type || props.feature?.category || "Unclassified";
});
const evidence = computed(() => props.feature?.evidence && typeof props.feature.evidence === "object" ? props.feature.evidence : {});
const coordinates = computed(() => {
  if (featureKind.value === "protein" || props.feature?.coordinates_available === false) return null;
  const start = finiteNumber(props.feature?.start);
  const end = finiteNumber(props.feature?.end);
  return start !== null && end !== null && start >= 1 && end >= start
    ? `${start.toLocaleString()}–${end.toLocaleString()} (1-based, inclusive)`
    : null;
});
const metadata = computed(() => [
  ["Result", result.value],
  ["Class", props.feature?.class ? `Class ${props.feature.class}` : null],
  ["Type", props.feature?.type],
  ["Subtype", props.feature?.subtype],
  ["Profile", props.feature?.profile],
  ["Contig", props.feature?.contig_id],
  ["Coordinates", coordinates.value],
  ["Strand", props.feature?.strand],
  ["Cassette", props.feature?.cassette_id],
  ["Residues", finiteNumber(props.feature?.residue_count) !== null ? `${finiteNumber(props.feature.residue_count).toLocaleString()} aa` : null],
  ["Repeats / spacers", finiteNumber(props.feature?.repeat_count) !== null ? `${finiteNumber(props.feature.repeat_count).toLocaleString()} / ${(finiteNumber(props.feature?.spacer_count) ?? 0).toLocaleString()}` : null],
  ["Category", props.feature?.category],
  ["Positive profile score", formatEvidence(props.feature?.profile_score)],
  ["Hard-negative score", formatEvidence(props.feature?.hard_negative_profile_score)],
  ["Score margin", formatEvidence(props.feature?.score_margin)],
  ["Decision threshold", formatEvidence(evidence.value.decision_threshold)],
  ["Profile hits", finiteNumber(evidence.value.profile_hits) !== null ? finiteNumber(evidence.value.profile_hits).toLocaleString() : null],
  ["Report E-value", formatEvalue(evidence.value.report_evalue)],
  ["Model", evidence.value.model_id],
].filter(([, value]) => value !== null && value !== undefined && value !== ""));

const arrayUnits = computed(() => {
  if (featureKind.value !== "crispr_array") return [];
  if (!Array.isArray(props.feature?.spacers)) return [];
  const spacers = props.feature.spacers;
  const units = [];
  for (let index = 0; index <= spacers.length; index += 1) {
    units.push({ kind: "repeat", label: `Repeat ${index + 1}` });
    if (index < spacers.length) units.push({ kind: "spacer", label: `Spacer ${index + 1}` });
  }
  return units;
});

function wrapped(sequence) {
  return String(sequence || "").match(/.{1,80}/g)?.join("\n") || "";
}

function safeHeaderToken(value, fallback = "feature") {
  const normalized = String(value || "").replace(/[^A-Za-z0-9_.:|=+\-]+/g, "_").slice(0, 240);
  return normalized || fallback;
}

function fallbackCopy(value) {
  if (typeof document === "undefined" || typeof document.execCommand !== "function") return false;
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  Object.assign(textarea.style, { position: "fixed", opacity: "0", pointerEvents: "none" });
  document.body.appendChild(textarea);
  textarea.select();
  let succeeded = false;
  try {
    succeeded = document.execCommand("copy");
  } catch {
    succeeded = false;
  } finally {
    textarea.remove();
  }
  return succeeded;
}

async function copySequence(sequence) {
  const value = String(sequence.sequence || "");
  if (!value) return;
  copyError.value = "";
  let succeeded = false;
  try {
    if (globalThis.navigator?.clipboard?.writeText) {
      await globalThis.navigator.clipboard.writeText(value);
      succeeded = true;
    }
  } catch {
    // A denied asynchronous clipboard request can still use the local selection fallback.
  }
  if (!succeeded) succeeded = fallbackCopy(value);
  if (!succeeded) {
    copyError.value = "The sequence could not be copied automatically. Select it in the sequence viewer and copy it manually.";
    copyAnnouncement.value = "Copy failed.";
    return;
  }
  copied.value = sequence.domKey;
  copyAnnouncement.value = `${sequence.label} copied.`;
  window.clearTimeout(copyTimer);
  copyTimer = window.setTimeout(() => {
    if (copied.value === sequence.domKey) copied.value = "";
  }, 1_800);
}

function downloadSequence(sequence) {
  const identifier = safeHeaderToken(featureId.value);
  const sequenceKey = safeHeaderToken(sequence.key, "sequence");
  const header = `>${identifier}|${sequenceKey} molecule=${safeHeaderToken(sequence.molecule)} orientation=${safeHeaderToken(sequence.orientation)}\n`;
  const extension = sequence.molecule === "protein" ? "faa" : "fna";
  saveBlob(
    new Blob([header, wrapped(sequence.sequence), "\n"], { type: "text/x-fasta;charset=utf-8" }),
    downloadName(`${identifier}-${sequence.key}.${extension}`),
  );
}

function downloadJson() {
  const identifier = safeHeaderToken(featureId.value);
  saveBlob(
    new Blob([`${JSON.stringify(props.feature, null, 2)}\n`], { type: "application/json;charset=utf-8" }),
    downloadName(`${identifier}.json`),
  );
}

watch(featureId, () => {
  copied.value = "";
  copyError.value = "";
  copyAnnouncement.value = "";
  window.clearTimeout(copyTimer);
});

onBeforeUnmount(() => window.clearTimeout(copyTimer));
</script>

<template>
  <aside class="feature-inspector" aria-labelledby="feature-inspector-heading" :aria-busy="loading">
    <p class="sr-only" role="status" aria-live="polite">{{ feature ? `Selected ${featureKind.replaceAll('_', ' ')} ${featureId}: ${result}` : 'No result feature selected.' }}</p>
    <p class="sr-only" role="status" aria-live="polite">{{ copyAnnouncement }}</p>
    <div v-if="feature" class="feature-inspector-heading">
      <div><p class="eyebrow">Selected {{ featureKind.replaceAll('_', ' ') }}</p><h4 id="feature-inspector-heading"><code>{{ featureId }}</code></h4></div>
      <button type="button" class="feature-json-button" :aria-label="`Download ${featureId} details as JSON`" @click="downloadJson"><AppIcon name="download" :size="16"/>JSON</button>
    </div>
    <p v-else id="feature-inspector-heading" class="feature-inspector-empty">Select a plotted feature to inspect its annotation and sequence contents.</p>

    <template v-if="feature">
      <p v-if="feature.is_cas === false" class="no-cas-explanation">No Cas profile passed the model decision rule. The competing profile evidence remains available for review.</p>
      <dl class="feature-metadata"><div v-for="([label, value]) in metadata" :key="label"><dt>{{ label }}</dt><dd>{{ value }}</dd></div></dl>

      <div v-if="arrayUnits.length" class="array-composition" aria-label="Alternating CRISPR consensus repeats and ordered spacers"><span v-for="(unit, index) in arrayUnits" :key="`${unit.kind}-${index}`" :class="unit.kind" :title="unit.label"><span class="sr-only">{{ unit.label }}</span></span></div>
      <p v-if="featureKind === 'cassette' && Array.isArray(feature.cas_protein_ids)" class="cassette-members"><strong>Cas proteins in this cassette</strong><code>{{ feature.cas_protein_ids.join(' → ') || 'None' }}</code></p>

      <p v-if="loading" class="feature-detail-state" role="status"><AppIcon name="refresh" :size="16"/>Loading authenticated sequence details…</p>
      <p v-else-if="error" class="feature-detail-error" role="alert">{{ error }}</p>
      <p v-else-if="!sequences.length && featureKind !== 'cassette'" class="feature-detail-state">Sequence detail is not present in this result. Use the checksummed bulk artifacts below.</p>
      <p v-if="copyError" class="feature-detail-error" role="alert">{{ copyError }}</p>

      <details v-for="(sequence, index) in sequences" :key="sequence.domKey" class="sequence-detail" :open="index === 0">
        <summary><span>{{ sequence.label }}</span><b>{{ Number(sequence.length).toLocaleString() }} {{ sequence.molecule === 'protein' ? 'aa' : 'nt' }}</b></summary>
        <div class="sequence-toolbar"><span>{{ sequence.orientation.replaceAll('_', ' ') }}<template v-if="sequence.sha256"> · SHA-256 <code>{{ sequence.sha256 }}</code></template></span><button type="button" :aria-label="`Copy ${sequence.label} sequence`" @click="copySequence(sequence)"><AppIcon name="copy" :size="15"/>{{ copied === sequence.domKey ? 'Copied' : 'Copy' }}</button><button type="button" :aria-label="`Download ${sequence.label} as FASTA`" @click="downloadSequence(sequence)"><AppIcon name="download" :size="15"/>FASTA</button></div>
        <pre class="sequence-viewer" tabindex="0" :aria-label="`${sequence.label} sequence`">{{ wrapped(sequence.sequence) }}</pre>
      </details>
    </template>
  </aside>
</template>

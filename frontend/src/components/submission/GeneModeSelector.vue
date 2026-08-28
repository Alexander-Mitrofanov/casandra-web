<script setup>
import { ANALYSIS_MODES } from "../../science.js";
import InfoTooltip from "../common/InfoTooltip.vue";

defineProps({
  modelValue: { type: String, required: true },
  includeCrisprArrays: Boolean,
});
defineEmits(["update:modelValue", "update:includeCrisprArrays"]);
</script>

<template>
  <fieldset class="mode-selector">
    <legend><span><b>1</b> Choose analysis</span></legend>
    <div class="mode-grid">
      <div v-for="mode in ANALYSIS_MODES" :key="mode.id" :class="['mode-card', { selected: modelValue === mode.id }]">
        <input :id="`analysis-mode-${mode.id}`" type="radio" name="analysis-mode" :value="mode.id" :checked="modelValue === mode.id" @change="$emit('update:modelValue', mode.id)"/>
        <label :for="`analysis-mode-${mode.id}`">
          <span class="mode-radio" aria-hidden="true"/>
          <span><small>{{ mode.label }}</small><strong>{{ mode.title }}</strong><em>{{ mode.detail }}</em><i>{{ mode.fit }}</i></span>
        </label>
        <InfoTooltip class="mode-card-help" :tooltip-id="`analysis-mode-help-${mode.id}`" :label="mode.helpLabel">
          <strong>{{ mode.title }}</strong>
          <p>{{ mode.helpIntro }}</p>
          <ol><li v-for="step in mode.helpSteps" :key="step">{{ step }}</li></ol>
          <p class="tooltip-note">{{ mode.helpNote }}</p>
        </InfoTooltip>
      </div>
    </div>
    <div v-if="modelValue === 'complete_genome'" class="array-option">
      <input id="include-crispr-arrays" type="checkbox" :checked="includeCrisprArrays" @change="$emit('update:includeCrisprArrays', $event.target.checked)"/>
      <label for="include-crispr-arrays"><span class="array-check" aria-hidden="true"/><span><strong>CRISPR array detection</strong><small>complement the analysis with CRISPR array detection</small></span></label>
      <InfoTooltip tooltip-id="crispridentify-help" label="About CRISPRidentify"><strong>CRISPR array detection</strong><p>CRISPRidentify runs independently on each submitted complete-genome sequence, validates candidate arrays, and reports accepted Bona-fide and Possible arrays with source-forward coordinates, repeat consensus, and spacers.</p><p class="tooltip-note">The overlay complements the map only: array proximity does not change or confirm a CasAndra Cas-gene or cassette call.</p></InfoTooltip>
    </div>
  </fieldset>
</template>

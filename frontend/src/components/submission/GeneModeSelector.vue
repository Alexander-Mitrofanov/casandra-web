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
        <InfoTooltip v-if="mode.help" class="mode-card-help" :tooltip-id="`analysis-mode-help-${mode.id}`" :label="mode.helpLabel">{{ mode.help }}</InfoTooltip>
      </div>
    </div>
    <div v-if="modelValue === 'complete_genome'" class="array-option">
      <input id="include-crispr-arrays" type="checkbox" :checked="includeCrisprArrays" @change="$emit('update:includeCrisprArrays', $event.target.checked)"/>
      <label for="include-crispr-arrays"><span class="array-check" aria-hidden="true"/><span><strong>CRISPR array detection</strong><small>complement the analysis with CRISPR array detection</small></span></label>
      <InfoTooltip tooltip-id="crispridentify-help" label="About CRISPRidentify">CRISPRidentify is an independent CRISPR array detector. It reports array coordinates and evidence categories alongside CasAndra; array proximity does not change or confirm CasAndra’s Cas calls.</InfoTooltip>
    </div>
  </fieldset>
</template>

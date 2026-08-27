<script setup>
import { GENE_MODES } from "../../science.js";

defineProps({ modelValue: { type: String, required: true } });
defineEmits(["update:modelValue"]);
</script>

<template>
  <fieldset class="mode-selector">
    <legend><span><b>1</b> Choose the gene-calling context</span><small>Mode-aware genetic code</small></legend>
    <div class="mode-grid">
      <label v-for="mode in GENE_MODES" :key="mode.id" :class="{ selected: modelValue === mode.id }">
        <input type="radio" name="gene-mode" :value="mode.id" :checked="modelValue === mode.id" @change="$emit('update:modelValue', mode.id)"/>
        <span class="mode-radio"/>
        <span><small>{{ mode.label }}</small><strong>{{ mode.title }}</strong><em>{{ mode.detail }}</em><i>{{ mode.fit }}</i></span>
      </label>
    </div>
  </fieldset>
</template>

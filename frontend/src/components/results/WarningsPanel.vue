<script setup>
import { asArray } from "../../utils/formatting.js";
import AppIcon from "../common/AppIcon.vue";
defineProps({ warnings: { type: Array, default: () => [] } });
</script>

<template>
  <section v-if="asArray(warnings).length" class="result-section warnings-panel" aria-labelledby="warnings-heading"><div class="warnings-title"><AppIcon name="warning"/><div><p class="eyebrow">Review flags</p><h3 id="warnings-heading">Scientific warnings</h3></div></div><ul><li v-for="(warning, index) in warnings" :key="index">{{ warning }}</li></ul></section>
</template>

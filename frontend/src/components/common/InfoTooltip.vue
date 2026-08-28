<script setup>
defineProps({
  tooltipId: { type: String, required: true },
  label: { type: String, required: true },
});
</script>

<template>
  <span class="info-tooltip">
    <button type="button" class="info-tooltip-trigger" :aria-label="label" :aria-describedby="tooltipId">?</button>
    <span :id="tooltipId" class="info-tooltip-content" role="tooltip"><slot/></span>
  </span>
</template>

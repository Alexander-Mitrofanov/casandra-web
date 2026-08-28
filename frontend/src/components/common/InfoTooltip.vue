<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";

defineProps({
  tooltipId: { type: String, required: true },
  label: { type: String, required: true },
});

const root = ref(null);
const open = ref(false);

function close() {
  open.value = false;
}

function onFocusOut(event) {
  if (!root.value?.contains(event.relatedTarget)) close();
}

function onDocumentPointerDown(event) {
  if (open.value && !root.value?.contains(event.target)) close();
}

onMounted(() => document.addEventListener("pointerdown", onDocumentPointerDown));
onBeforeUnmount(() => document.removeEventListener("pointerdown", onDocumentPointerDown));
</script>

<template>
  <span ref="root" :class="['info-tooltip', { open }]" @mouseenter="open = true" @mouseleave="close" @focusin="open = true" @focusout="onFocusOut" @keydown.esc.stop="close">
    <button type="button" class="info-tooltip-trigger" :aria-label="label" :aria-controls="tooltipId" :aria-expanded="open" @click.stop="open = !open"><span aria-hidden="true">?</span></button>
    <span v-if="open" :id="tooltipId" class="info-tooltip-content" role="region" :aria-label="label"><slot/></span>
  </span>
</template>

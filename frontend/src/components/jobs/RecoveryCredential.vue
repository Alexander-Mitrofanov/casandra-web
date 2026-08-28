<script setup>
import { computed, ref } from "vue";

import { buildJobRecoveryLink } from "../../jobStore.js";
import AppIcon from "../common/AppIcon.vue";

const props = defineProps({ credential: { type: Object, required: true } });
const linkField = ref(null);
const copyStatus = ref("");
const appUrl = new URL(import.meta.env.BASE_URL, window.location.origin).href;
const recoveryLink = computed(() => buildJobRecoveryLink(props.credential, appUrl));

async function copyLink() {
  try {
    if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
    await navigator.clipboard.writeText(recoveryLink.value);
    copyStatus.value = "Private link copied.";
  } catch {
    linkField.value?.focus();
    linkField.value?.select();
    copyStatus.value = "Link selected. Copy it manually.";
  }
}
</script>

<template>
  <div class="credential-notice" role="note" aria-label="Private analysis link">
    <AppIcon name="shield"/>
    <div class="credential-copy"><strong>Save your private analysis link</strong><p>Use it to return to this analysis. Anyone with the link can access it while it is available.</p><label for="recovery-link">Private analysis link</label><input id="recovery-link" ref="linkField" :value="recoveryLink" readonly @focus="$event.currentTarget.select()"/></div>
    <button type="button" @click="copyLink"><AppIcon name="copy" :size="16"/>Copy private link</button>
    <span class="sr-only" aria-live="polite">{{ copyStatus }}</span>
  </div>
</template>

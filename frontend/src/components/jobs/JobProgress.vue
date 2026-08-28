<script setup>
import { computed } from "vue";

import { PHASES, TERMINAL_STATUSES, phaseIndex } from "../../science.js";
import AppIcon from "../common/AppIcon.vue";
import RecoveryCredential from "./RecoveryCredential.vue";

const props = defineProps({
  job: { type: Object, required: true },
  credential: { type: Object, required: true },
  cancelling: Boolean,
});
defineEmits(["cancel", "forget"]);

const terminal = computed(() => TERMINAL_STATUSES.has(props.job?.status));
const successful = computed(() => props.job?.status === "completed");
const currentIndex = computed(() => phaseIndex(props.job?.phase || (props.job?.status === "completed" ? "completed" : "queued")));
const statusTitle = computed(() => ({
  queued: "Analysis queued",
  running: "Analysis running",
  completed: "Analysis complete",
  failed: "Analysis failed",
  cancelled: "Analysis cancelled",
})[props.job?.status] || "Waiting for job status");
</script>

<template>
  <section :class="['job-panel', `job-${job?.status || 'queued'}`]" aria-labelledby="job-heading">
    <div class="job-heading"><div><p class="eyebrow">Your analysis</p><h2 id="job-heading" tabindex="-1">{{ statusTitle }}</h2></div><span :class="['job-badge', successful ? 'success' : terminal ? 'terminal' : 'active']" role="status"><i/>{{ successful ? 'Results ready' : terminal ? statusTitle : job?.queue_position ? `Queue ${job.queue_position}` : 'In progress' }}</span></div>
    <RecoveryCredential :credential="credential"/>
    <ol v-if="!terminal" class="stage-list" aria-label="Analysis progress"><li v-for="(phase, index) in PHASES.slice(0, -1)" :key="phase.id" :class="index < currentIndex ? 'complete' : index === currentIndex ? 'current' : 'pending'" :aria-current="index === currentIndex ? 'step' : undefined"><span><AppIcon v-if="index < currentIndex" name="check" :size="15"/><template v-else>{{ index + 1 }}</template></span><div><strong>{{ phase.label }}</strong><small>{{ phase.detail }}</small></div></li></ol>
    <div v-if="!terminal" class="queue-row"><span>{{ job?.cancel_requested ? 'Cancellation requested; the analysis will stop safely.' : 'You can close this tab after saving the private link above.' }}</span><button class="cancel-button" type="button" :disabled="cancelling || job?.cancel_requested" @click="$emit('cancel')"><AppIcon name="stop" :size="16"/>{{ cancelling ? 'Cancelling…' : job?.cancel_requested ? 'Cancellation requested' : 'Cancel job' }}</button></div>
    <div v-if="job?.status === 'failed'" class="job-message error" role="alert"><AppIcon name="warning"/><div><strong>The workflow did not complete</strong><p>{{ job.error?.message || job.error || 'The service reported an analysis failure.' }}</p></div></div>
    <div v-if="job?.status === 'cancelled'" class="job-message"><AppIcon name="info"/><div><strong>Job cancelled</strong><p>Partial working files are not presented as scientific results.</p></div></div>
    <div v-if="terminal" class="queue-row"><span>Download any files you need before the results expire.</span><button class="leave-job-button" type="button" @click="$emit('forget')">Leave analysis and start another</button></div>
  </section>
</template>

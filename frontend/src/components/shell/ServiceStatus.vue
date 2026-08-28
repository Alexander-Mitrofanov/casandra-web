<script setup>
import AppIcon from "../common/AppIcon.vue";

defineProps({ service: { type: Object, required: true } });
defineEmits(["refresh"]);
</script>

<template>
  <div :class="['service-status', `service-${service.state}`]" role="status">
    <span class="service-dot"/>
    <strong>{{ service.state === 'checking' ? 'Checking service' : service.state === 'online' ? 'Service ready' : service.state === 'degraded' ? 'Service degraded' : 'Service unavailable' }}</strong>
    <button v-if="service.state === 'offline'" type="button" aria-label="Check the service again" @click="$emit('refresh')"><AppIcon name="refresh" :size="15"/></button>
  </div>
</template>

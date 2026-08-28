<script setup>
import ServiceStatus from "./ServiceStatus.vue";

defineProps({ service: { type: Object, required: true } });
defineEmits(["refresh"]);
</script>

<template>
  <header class="hero">
    <div class="topbar">
      <ServiceStatus :service="service" @refresh="$emit('refresh')"/>
    </div>
    <div class="hero-content">
      <div class="hero-copy">
        <h1 aria-label="CasAndra. Cas proteins detection, annotation and classification pipeline">
          <span class="hero-product">CasAndra</span>
          <span class="hero-statement">Cas proteins detection, annotation and classification pipeline</span>
        </h1>
      </div>
    </div>
  </header>
</template>

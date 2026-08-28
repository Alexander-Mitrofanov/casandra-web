<script setup>
import BrandMark from "../common/BrandMark.vue";
import ServiceStatus from "./ServiceStatus.vue";

defineProps({ service: { type: Object, required: true } });
defineEmits(["refresh"]);
</script>

<template>
  <header class="hero">
    <nav class="topbar" aria-label="Main navigation">
      <a class="brand" href="#top" aria-label="CasAndra home"><BrandMark/><span><strong>CasAndra</strong><small>your Cas predicting oracle</small></span></a>
      <ServiceStatus :service="service" @refresh="$emit('refresh')"/>
    </nav>
    <div class="hero-content">
      <h1>CasAndra <span>— Cas proteins detection, annotation and classification pipeline</span></h1>
    </div>
  </header>
</template>

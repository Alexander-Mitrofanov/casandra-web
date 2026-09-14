<script setup>
import ServiceStatus from "./ServiceStatus.vue";
import BrandMark from "../common/BrandMark.vue";

defineProps({ service: { type: Object, required: true } });
defineEmits(["refresh"]);
</script>

<template>
  <header class="hero">
    <div class="topbar">
      <div class="brand-identity">
        <BrandMark/>
        <div class="brand-copy">
          <h1 aria-label="CasAndra. Cas proteins detection, annotation and classification pipeline"><a class="brand-link" href="#top" aria-label="CasAndra home">CasAndra</a></h1>
          <p class="hero-statement">Detect, annotate, and classify Cas proteins from nucleotide or protein FASTA.</p>
        </div>
      </div>
      <ServiceStatus :service="service" @refresh="$emit('refresh')"/>
    </div>
  </header>
</template>

<script setup>
import ServiceStatus from "./ServiceStatus.vue";
import BrandMark from "../common/BrandMark.vue";

defineProps({ service: { type: Object, required: true } });
defineEmits(["refresh"]);
</script>

<template>
  <header class="hero">
    <div class="topbar">
      <a class="brand-link" href="#top" aria-label="CasAndra home"><BrandMark/><span>CasAndra</span></a>
      <span class="header-context">Sequence analysis workspace</span>
      <ServiceStatus :service="service" @refresh="$emit('refresh')"/>
    </div>
    <div class="hero-content">
      <div class="hero-copy">
        <h1 aria-label="CasAndra. Cas proteins detection, annotation and classification pipeline">
          <span class="hero-product">Find the Cas in your sequence.</span>
          <span class="hero-statement">Detect, annotate, and classify Cas proteins from nucleotide or protein FASTA.</span>
        </h1>
      </div>
    </div>
  </header>
</template>

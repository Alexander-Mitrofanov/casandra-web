<script setup>
import BrandMark from "../common/BrandMark.vue";
import ServiceStatus from "./ServiceStatus.vue";

defineProps({ service: { type: Object, required: true } });
defineEmits(["refresh"]);

const mosaicSrc = `${import.meta.env.BASE_URL}og.png?v=b9b841a9`;
</script>

<template>
  <header class="hero">
    <nav class="topbar" aria-label="Main navigation">
      <a class="brand" href="#top" aria-label="CasAndra home"><BrandMark/><span><strong>CasAndra</strong><small>Your Cas predicting oracle</small></span></a>
      <ServiceStatus :service="service" @refresh="$emit('refresh')"/>
    </nav>
    <div class="hero-content">
      <div class="hero-copy">
        <p class="hero-kicker">Cas intelligence, made explorable.</p>
        <h1><span class="hero-product">CasAndra</span> <span class="hero-statement">— Cas proteins detection, annotation and classification pipeline</span></h1>
        <p class="hero-intro">Move from raw FASTA to interactive Cas annotations, cassette classification, and optional CRISPR array context in one focused workspace.</p>
        <ul class="hero-capabilities" aria-label="CasAndra capabilities"><li>Four focused analyses</li><li>Interactive gene maps</li><li>FASTA, CSV, and JSON</li></ul>
      </div>
      <figure class="hero-visual hero-mosaic">
        <img
          :src="mosaicSrc"
          width="1730"
          height="909"
          alt="Damaged ancient-Greek CasAndra mosaic showing seven CRISPR–Cas classification bands between symmetrical pillars."
        />
      </figure>
    </div>
  </header>
</template>

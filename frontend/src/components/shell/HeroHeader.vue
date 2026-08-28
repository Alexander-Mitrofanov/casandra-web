<script setup>
import BrandMark from "../common/BrandMark.vue";
import AppIcon from "../common/AppIcon.vue";
import ServiceStatus from "./ServiceStatus.vue";

defineProps({ service: { type: Object, required: true } });
defineEmits(["refresh"]);
</script>

<template>
  <header class="hero">
    <nav class="topbar" aria-label="Main navigation">
      <a class="brand" href="#top" aria-label="CasAndra home"><BrandMark/><span><strong>CasAndra</strong><small>Your Cas predicting oracle</small></span></a>
      <a class="topbar-action" href="#workflow">Start analysis</a>
      <ServiceStatus :service="service" @refresh="$emit('refresh')"/>
    </nav>
    <div class="hero-content">
      <div class="hero-copy">
        <p class="hero-kicker">Cas intelligence, made explorable.</p>
        <h1><span class="hero-product">CasAndra</span> <span class="hero-statement">— Cas proteins detection, annotation and classification pipeline</span></h1>
        <p class="hero-intro">Move from raw FASTA to interactive Cas annotations, cassette classification, and optional CRISPR array context in one focused workspace.</p>
        <a class="hero-primary" href="#workflow"><span>Start with a sequence</span><AppIcon name="arrow" :size="18"/></a>
        <ul class="hero-capabilities" aria-label="CasAndra capabilities"><li>Four focused analyses</li><li>Interactive gene maps</li><li>FASTA, CSV, and JSON</li></ul>
      </div>
      <div class="hero-visual" aria-hidden="true">
        <div class="hero-visual-head"><span>Sequence overview</span><b><i/>analysis ready</b></div>
        <div class="hero-genome-stage">
          <span class="hero-axis-start">5′</span><span class="hero-axis-end">3′</span>
          <i class="hero-gene hero-gene-one">Cas3</i><i class="hero-gene hero-gene-two">Cas5</i><i class="hero-gene hero-gene-three">Cas7</i><i class="hero-array"/>
        </div>
        <div class="hero-visual-foot"><span><i class="hero-cas-key"/>Cas genes</span><span><i class="hero-array-key"/>CRISPR array</span><strong>Source-forward view</strong></div>
      </div>
    </div>
  </header>
</template>

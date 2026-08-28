<script setup>
import BrandMark from "../common/BrandMark.vue";
import ServiceStatus from "./ServiceStatus.vue";

defineProps({ service: { type: Object, required: true } });
defineEmits(["refresh"]);
</script>

<template>
  <header class="hero">
    <nav class="topbar" aria-label="Main navigation">
      <a class="brand" href="#top" aria-label="CasAndra home"><BrandMark/><span><strong>CasAndra</strong><small>Cas gene explorer</small></span></a>
      <div class="nav-links"><a href="#workflow">Analyze</a><a href="#interpretation">Interpretation</a></div>
      <ServiceStatus :service="service" @refresh="$emit('refresh')"/>
    </nav>
    <div class="hero-content">
      <div class="hero-copy">
        <p class="kicker"><span/>CAS PROTEINS · CASSETTES · ARRAY CONTEXT</p>
        <h1>See the <em>Cas system</em><br/>in its genomic neighborhood.</h1>
        <p class="hero-lead">CasAndra identifies Cas genes and cassette architecture. CRISPRidentify v2 adds nearby array calls so every prediction can be inspected on the source-forward contig.</p>
        <div class="hero-actions"><a class="hero-primary" href="#workflow">Analyze nucleotide FASTA</a><a class="hero-secondary" href="#interpretation">How to interpret calls <span aria-hidden="true">↓</span></a></div>
      </div>
      <div class="hero-visual" aria-label="Illustration of a Cas cassette beside a CRISPR array">
        <div class="visual-label label-cassette">CAS CASSETTE</div>
        <div class="visual-track"><i/><span class="gene gene-a">cas3</span><span class="gene gene-b">cse1</span><span class="gene gene-c">cas7</span><span class="gene gene-d">cas5</span></div>
        <div class="visual-label label-array">CRISPR ARRAY</div>
        <div class="repeat-track"><i v-for="n in 6" :key="n"/><span v-for="n in 5" :key="`s${n}`"/></div>
        <div class="visual-axis"><span>5′</span><i/><span>3′</span></div>
        <p>Source-forward genomic view</p>
      </div>
    </div>
  </header>
</template>

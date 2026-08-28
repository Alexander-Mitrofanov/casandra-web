<script setup>
import { SCIENTIFIC_CAVEATS } from "../../science.js";
import AppIcon from "../common/AppIcon.vue";
</script>

<template>
  <section id="interpretation" class="science-section" aria-labelledby="interpretation-heading">
    <div class="section-intro compact"><p class="eyebrow">Interpretation</p><h2 id="interpretation-heading">Strong evidence, bounded claims.</h2><p>The interface keeps protein evidence, cassette classification, and CRISPR-array context distinct.</p></div>
    <div class="interpret-grid">
      <article><span class="article-number">01</span><h3>Cas protein call</h3><p>A sequence-model decision supported by the reported profile and score margin. Inspect edge-truncated ORFs carefully.</p></article>
      <article><span class="article-number">02</span><h3>Cassette call</h3><p>A source-coordinate neighborhood whose gene composition supports a class, type, or subtype assignment.</p></article>
      <article><span class="article-number">03</span><h3>Array context</h3><p>A CRISPRidentify v2 array on the same contig. Proximity is visible, but biological linkage is not assumed.</p></article>
    </div>
    <div class="caveat-panel" role="note" aria-label="Scientific limitations"><AppIcon name="warning"/><div><h3>Read before using the result</h3><ul><li v-for="item in SCIENTIFIC_CAVEATS" :key="item">{{ item }}</li></ul></div></div>
  </section>
</template>

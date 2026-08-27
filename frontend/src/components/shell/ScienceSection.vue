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

  <section id="methods" class="methods-section" aria-labelledby="methods-heading">
    <div><p class="eyebrow">Method boundary</p><h2 id="methods-heading">Two detectors, one coordinate system.</h2></div>
    <div class="method-flow" aria-label="Analysis stages"><span><b>01</b>Nucleotide FASTA<small>source records</small></span><i>→</i><span><b>02</b>CasAndra<small>genes + cassettes</small></span><i>→</i><span><b>03</b>CRISPRidentify v2<small>array calls</small></span><i>→</i><span><b>04</b>Integrated report<small>no forced linkage</small></span></div>
    <p class="method-note">The service requests translation table 11 for single-mode Pyrodigal training. Meta mode can select a genetic code per gene; the selected mode and observed tables are reported with each result. Use <strong>Auto</strong> for complete genomic records and <strong>Meta</strong> for short or fragmented contigs. This research interface is not intended for clinical or safety-critical decisions.</p>
  </section>
</template>

<script setup>
import BrandMark from "../common/BrandMark.vue";
defineProps({ service: { type: Object, required: true } });
</script>

<template>
  <footer class="site-footer">
    <div class="footer-brand"><BrandMark/><div><strong>CasAndra</strong><span>Cas gene identification and genomic context</span></div></div>
    <div class="footer-notes">
      <p>Research software · Results require expert review · API {{ service.version || 'version unavailable' }}</p>
      <p class="art-credit">
        Classification artwork adapted from
        <a href="https://www.nature.com/articles/s41564-025-02180-8" rel="noreferrer">Makarova et al. (2025)</a>
        under <a href="https://creativecommons.org/licenses/by/4.0/" rel="noreferrer">CC BY 4.0</a>; modified for CasAndra.
      </p>
    </div>
    <a href="#top">Back to top ↑</a>
  </footer>
</template>

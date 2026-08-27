<script setup>
import BrandMark from "../common/BrandMark.vue";
defineProps({ service: { type: Object, required: true } });
</script>

<template>
  <footer class="site-footer"><div class="footer-brand"><BrandMark/><div><strong>CasAndra</strong><span>Cas gene identification and genomic context</span></div></div><p>Research software · Results require expert review · API {{ service.version || 'version unavailable' }}</p><a href="#top">Back to top ↑</a></footer>
</template>

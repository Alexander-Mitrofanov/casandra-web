<script setup>
defineProps({ service: { type: Object, required: true } });
</script>

<template>
  <footer class="site-footer">
    <p>{{ service.casandraVersion ? `CasAndra v${service.casandraVersion}` : 'CasAndra version unavailable' }}</p>
  </footer>
</template>

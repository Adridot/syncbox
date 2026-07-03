<script setup lang="ts">
// Skeleton shimmer rows (SPEC-DESIGN §7.4 — shimmer 1.3s, no decoration).
withDefaults(defineProps<{ rows?: number }>(), { rows: 4 })
</script>

<template>
  <div class="loading" role="status" :aria-label="$t('common.loading')">
    <div v-for="row in rows" :key="row" class="skeleton-row" />
  </div>
</template>

<style scoped>
.loading {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px 0;
}
.skeleton-row {
  height: 38px;
  border-radius: var(--radius-inner);
  background: linear-gradient(90deg, var(--surface-raised) 25%, #161a24 50%, var(--surface-raised) 75%);
  background-size: 400px 100%;
  animation: shimmer var(--motion-shimmer) linear infinite;
}
</style>

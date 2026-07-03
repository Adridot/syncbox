<script setup lang="ts">
// Missing-track resolution scope (SPEC-DESIGN §6): library / event / collection.
defineProps<{ scope: 'library' | 'event' | 'collection' }>()
</script>

<template>
  <span class="badge">{{ $t(`scope.${scope}`) }}</span>
</template>

<style scoped>
.badge {
  display: inline-block;
  font-size: var(--size-meta);
  font-family: var(--font-mono);
  border-radius: 7px;
  padding: 2.5px 8px;
  background: var(--neutral-tint);
  border: 1px solid var(--neutral-border);
  color: var(--text-secondary-bright);
  white-space: nowrap;
}
</style>

<script setup lang="ts">
// Illustrated empty state (SPEC-DESIGN §6) — per-domain copy via props/slot.
defineProps<{ icon?: string; title: string; body?: string }>()
</script>

<template>
  <div class="empty">
    <div class="glyph">{{ icon ?? '◌' }}</div>
    <h3>{{ title }}</h3>
    <p v-if="body">{{ body }}</p>
    <div class="actions"><slot /></div>
  </div>
</template>

<style scoped>
.empty {
  text-align: center;
  padding: 48px 24px;
  color: var(--text-secondary);
}
.glyph {
  width: 52px;
  height: 52px;
  border-radius: var(--radius-card);
  background: var(--surface-raised);
  border: 1px solid var(--border);
  display: grid;
  place-content: center;
  font-size: 22px;
  margin: 0 auto 14px;
  color: var(--text-muted-bright);
}
h3 {
  font: var(--text-h3);
  color: var(--text-primary);
  margin: 0;
}
p {
  font-size: 13px;
  margin: 6px auto 0;
  max-width: 360px;
  line-height: 1.5;
}
.actions {
  margin-top: 16px;
}
</style>

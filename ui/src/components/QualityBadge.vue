<script setup lang="ts">
// 3-level quality verdict (SPEC-UNIFIED §5.12): ok / lossy probable /
// UNCERTAIN — the uncertain level is a cautious violet-gray, NEVER red.
const props = defineProps<{ verdict: 'ok' | 'lossy_source_probable' | 'incertain' }>()

const TONE = {
  ok: 'success',
  lossy_source_probable: 'warning',
  incertain: 'uncertain',
} as const

const tone = TONE[props.verdict] ?? 'uncertain'
</script>

<template>
  <span class="badge" :data-tone="tone">{{ $t(`quality.${verdict}`) }}</span>
</template>

<style scoped>
.badge {
  display: inline-block;
  font-size: var(--size-meta);
  font-weight: 500;
  border-radius: 7px;
  padding: 2.5px 8px;
  white-space: nowrap;
}
.badge[data-tone='success'] {
  background: var(--success-tint);
  border: 1px solid var(--success-border);
  color: var(--success);
}
.badge[data-tone='warning'] {
  background: var(--warning-tint);
  border: 1px solid var(--warning-border);
  color: var(--warning-text);
}
.badge[data-tone='uncertain'] {
  background: var(--uncertain-tint);
  border: 1px solid var(--uncertain-border);
  color: var(--uncertain);
}
</style>

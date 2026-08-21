<script setup lang="ts">
// Shared status vocabulary for tracks AND events (SPEC-DESIGN §6/§9 —
// one component, coherent tones; distinct labels live in i18n).
import { computed } from 'vue'

const props = defineProps<{ status: string }>()

const TONES: Record<string, string> = {
  new: 'neutral',
  matched: 'accent',
  conflict: 'warning',
  ambiguous: 'warning',
  ready: 'teal',
  imported: 'success',
  missing: 'danger',
  acquisition_failed: 'danger',
  removed_from_source: 'muted',
  // same tone as its library twin, and deliberately NOT the warning amber of
  // the pending delta: a departure is a decision, not work to re-apply
  removed_upstream: 'muted',
  ignored: 'muted',
  purchase_link_unavailable: 'muted',
  manual_relink_needed: 'warning',
  pending: 'neutral',
  applied: 'success',
  partially_applied: 'warning',
}

const tone = computed(() => TONES[props.status] ?? 'neutral')
</script>

<template>
  <span class="badge" :data-tone="tone">{{ $t(`status.${status}`) }}</span>
</template>

<style scoped>
.badge {
  display: inline-block;
  font-size: var(--size-meta);
  font-weight: 500;
  border-radius: 7px;
  padding: 2.5px 8px;
  white-space: nowrap;
  background: var(--neutral-tint);
  border: 1px solid var(--neutral-border);
  color: var(--text-secondary-bright);
}
.badge[data-tone='accent'] {
  background: var(--accent-tint);
  border-color: var(--accent-border);
  color: var(--accent-hover);
}
.badge[data-tone='teal'] {
  background: var(--teal-tint);
  border-color: var(--teal-border);
  color: var(--teal);
}
.badge[data-tone='success'] {
  background: var(--success-tint);
  border-color: var(--success-border);
  color: var(--success);
}
.badge[data-tone='warning'] {
  background: var(--warning-tint);
  border-color: var(--warning-border);
  color: var(--warning-text);
}
.badge[data-tone='danger'] {
  background: var(--danger-tint);
  border-color: var(--danger-border);
  color: var(--danger-text);
}
.badge[data-tone='muted'] {
  color: var(--text-muted-bright);
}
</style>

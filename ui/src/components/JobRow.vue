<script setup lang="ts">
// Live job row: the bar width IS the real SSE pct (F16 — never derived
// from tone/status; never faked). Reads the jobs store by kind.
import { computed } from 'vue'

import { useJobsStore } from '../stores/jobs'

const props = defineProps<{ kind: string; label: string }>()
const jobs = useJobsStore()

const progress = computed(() => jobs.progressOf(props.kind))
</script>

<template>
  <div v-if="progress" class="job-row">
    <span class="label">{{ label }}</span>
    <div class="track">
      <div class="bar" :style="{ width: `${progress.pct}%` }" />
    </div>
    <span class="pct">{{ progress.pct }}%</span>
  </div>
</template>

<style scoped>
.job-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: var(--row-padding-y) 0;
}
.label {
  font-size: 13px;
  color: var(--text-secondary-bright);
  flex: none;
}
.track {
  flex: 1;
  height: 8px;
  border-radius: 5px;
  background: var(--surface-raised);
  border: 1px solid var(--border-subtle-2);
  overflow: hidden;
}
.bar {
  height: 100%;
  border-radius: 5px;
  background: repeating-linear-gradient(
    45deg,
    var(--accent),
    var(--accent) 8px,
    var(--accent-hover) 8px,
    var(--accent-hover) 16px
  );
  background-size: 24px 24px;
  animation: barflow 0.9s linear infinite;
  transition: width 0.25s ease;
}
.pct {
  font-family: var(--font-mono);
  font-size: var(--size-meta);
  color: var(--text-secondary-bright);
  min-width: 38px;
  text-align: right;
}
</style>

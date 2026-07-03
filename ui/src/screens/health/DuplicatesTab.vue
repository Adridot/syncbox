<script setup lang="ts">
// Doublons tab (SPEC-DESIGN §2/§6): explicit scan CTA with SSE progress
// (the scan locks the whole API — never auto-run), DuplicateGroupCard per
// group, per-group resolve with the 428 permanent-delete consent loop,
// dismiss. A 409 stale_snapshot on resolve prompts a re-scan.
import { useI18n } from 'vue-i18n'

import DuplicateGroupCard from '../../components/DuplicateGroupCard.vue'
import JobRow from '../../components/JobRow.vue'
import { useDuplicatesStore } from '../../stores/duplicates'
import { useHealthStore } from '../../stores/health'

const { t } = useI18n()
const duplicates = useDuplicatesStore()
const health = useHealthStore()

async function scan() {
  await duplicates.scan()
  health.setDuplicateGroups(duplicates.groups?.length ?? 0)
}
</script>

<template>
  <div>
    <div class="intro">{{ t('duplicates.intro') }}</div>

    <div class="scan-bar">
      <button class="btn-accent" :disabled="duplicates.scanning" @click="scan">
        {{ duplicates.scanning ? t('duplicates.scanning') : t('duplicates.scan') }}
      </button>
      <JobRow class="scan-progress" kind="duplicates.scan" :label="t('duplicates.scanLabel')" />
    </div>

    <div v-if="duplicates.groups === null" class="hint">{{ t('duplicates.notScanned') }}</div>
    <div v-else-if="!duplicates.groups.length" class="hint">{{ t('duplicates.clean') }}</div>

    <div v-else class="groups">
      <DuplicateGroupCard
        v-for="(group, index) in duplicates.groups"
        :key="group.key"
        :group="group"
        :index="index"
        @stale="scan"
      />
      <div class="per-group">{{ t('duplicates.perGroup') }}</div>
    </div>
  </div>
</template>

<style scoped>
.intro {
  font-size: 12.5px;
  color: var(--text-muted-bright);
  margin-bottom: 14px;
  line-height: 1.5;
}
.scan-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}
.btn-accent {
  background: var(--accent);
  border: none;
  color: #06131f;
  padding: 9px 16px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  flex: none;
}
.btn-accent:disabled {
  opacity: 0.6;
  cursor: default;
}
.scan-progress {
  flex: 1;
}
.hint {
  font-size: 13px;
  color: var(--text-muted);
  padding: 24px 0;
  text-align: center;
}
.groups {
  display: flex;
  flex-direction: column;
  gap: 22px;
}
.per-group {
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
}
</style>

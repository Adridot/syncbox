<script setup lang="ts">
// RB-open mutation guard, made READABLE instead of silently graying buttons
// (SPEC-DESIGN §3.5): friendly banner + "J'ai fermé Rekordbox" -> immediate
// re-poll of /api/status. Never shows PID/path/flag (§8).
import { useI18n } from 'vue-i18n'

import { useStatusStore } from '../stores/status'

const { t } = useI18n()
const status = useStatusStore()
</script>

<template>
  <div class="banner" role="status">
    <span class="icon">☕</span>
    <p class="text">
      <strong>{{ t('rbGuard.title') }}</strong>
      <span class="body">{{ t('rbGuard.body') }}</span>
    </p>
    <button class="confirm" @click="status.refresh()">{{ t('rbGuard.confirm') }}</button>
  </div>
</template>

<style scoped>
.banner {
  background: linear-gradient(90deg, rgba(245, 181, 68, 0.16), rgba(245, 181, 68, 0.06));
  border-bottom: 1px solid var(--warning-border);
  padding: 11px 24px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.icon {
  font-size: 16px;
}
.text {
  flex: 1;
  margin: 0;
}
strong {
  font-weight: 600;
  color: var(--warning-text);
}
.body {
  color: var(--text-secondary);
  margin-left: 8px;
  font-size: 13px;
}
.confirm {
  background: rgba(245, 181, 68, 0.18);
  color: var(--warning-text);
  border: 1px solid rgba(245, 181, 68, 0.35);
  padding: 6px 13px;
  border-radius: var(--radius-control);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
</style>

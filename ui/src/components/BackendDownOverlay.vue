<script setup lang="ts">
// Full-screen overlay after the supervisor exhausted its bounded restarts
// (SPEC-DESIGN §5). "Relancer" invokes the shell's restart_sidecar command,
// then polls /api/status until the sidecar answers again.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { restartSidecar } from '../shell'
import { useStatusStore } from '../stores/status'

const { t } = useI18n()
const status = useStatusStore()
const restarting = ref(false)

async function relaunch() {
  restarting.value = true
  await restartSidecar()
  for (let attempt = 0; attempt < 20 && status.backendDown; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, 500))
    await status.refresh()
  }
  restarting.value = false
}
</script>

<template>
  <div class="overlay" role="alertdialog" :aria-label="t('backendDown.title')">
    <div class="box">
      <div class="glyph">⚠</div>
      <h2>{{ t('backendDown.title') }}</h2>
      <p>{{ t('backendDown.body') }}</p>
      <button class="retry" :disabled="restarting" @click="relaunch">
        {{ restarting ? t('backendDown.retrying') : t('backendDown.retry') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: absolute;
  inset: 0;
  background: rgba(8, 10, 14, 0.92);
  backdrop-filter: blur(3px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.box {
  text-align: center;
  max-width: 380px;
  padding: 32px;
}
.glyph {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-card);
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  display: grid;
  place-content: center;
  font-size: 26px;
  margin: 0 auto 18px;
}
h2 {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
}
p {
  color: var(--text-secondary);
  font-size: 14px;
  margin-top: 8px;
  line-height: 1.5;
}
.retry {
  margin-top: 20px;
  background: var(--accent);
  color: #06131f;
  border: none;
  padding: 11px 22px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}
.retry:disabled {
  opacity: 0.6;
  cursor: default;
}
</style>

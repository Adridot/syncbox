<script setup lang="ts">
// Smart Fixes tab (SPEC-DESIGN §2/§6, SPEC-UNIFIED §5.11): the catalog is
// FIXED server-side (mockup's 4 per-family checkboxes are not selectable) —
// render families as descriptive text + ONE dry-run CTA -> DryRunModal.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import DryRunModal from '../../components/DryRunModal.vue'

const { t } = useI18n()
const showDryRun = ref(false)

const FAMILIES = [
  'extractArtist',
  'normalizeCase',
  'stripJunk',
  'fixEncoding',
] as const
</script>

<template>
  <div class="card">
    <h3>{{ t('smartfixes.title') }}</h3>
    <p class="lede">{{ t('smartfixes.lede') }}</p>
    <div class="families">
      <div v-for="family in FAMILIES" :key="family" class="family">
        <span class="tick">✓</span>{{ t(`smartfixes.families.${family}`) }}
      </div>
    </div>
    <div class="footer">
      <div class="protected-note">🔒 {{ t('smartfixes.protectedNote') }}</div>
      <button class="btn-teal" @click="showDryRun = true">{{ t('smartfixes.runDryRun') }}</button>
    </div>

    <DryRunModal v-if="showDryRun" @close="showDryRun = false" @executed="showDryRun = false" />
  </div>
</template>

<style scoped>
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 20px;
}
h3 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 6px;
}
.lede {
  color: var(--text-muted-bright);
  font-size: 13px;
  line-height: 1.5;
  max-width: 560px;
  margin: 0;
}
.families {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
}
.family {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 10px;
  padding: 12px;
  font-size: 13px;
  color: var(--text-secondary-bright);
}
.tick {
  color: var(--teal);
}
.footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 18px;
}
.protected-note {
  font-size: 12.5px;
  color: var(--text-muted-bright);
}
.btn-teal {
  background: var(--teal);
  border: none;
  color: #06131f;
  padding: 10px 18px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
</style>

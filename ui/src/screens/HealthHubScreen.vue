<script setup lang="ts">
// Santé de collection (M4.9 — SPEC-DESIGN §2): the Doctor hub. Deep-linkable
// tab bar (#/health/<tab>); tab badges derive from the ONE canonical health
// selector — no second counter definition anywhere.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { HEALTH_TABS, type HealthTab } from '../router'
import { useHealthStore } from '../stores/health'
import BackupsTab from './health/BackupsTab.vue'
import DuplicatesTab from './health/DuplicatesTab.vue'
import MissingTab from './health/MissingTab.vue'
import SmartFixesTab from './health/SmartFixesTab.vue'
import UntaggedTab from './health/UntaggedTab.vue'

const props = defineProps<{ tab?: string }>()
const { t } = useI18n()
const router = useRouter()
const health = useHealthStore()

const TAB_COMPONENTS = {
  duplicates: DuplicatesTab,
  missing: MissingTab,
  untagged: UntaggedTab,
  smartfixes: SmartFixesTab,
  backups: BackupsTab,
} as const

const active = computed<HealthTab>(() =>
  HEALTH_TABS.includes(props.tab as HealthTab) ? (props.tab as HealthTab) : 'duplicates',
)

const badges = computed<Record<HealthTab, number | null>>(() => ({
  duplicates: health.badges.duplicates,
  missing: health.missingCounts?.collection ?? null,
  untagged: health.badges.untagged,
  smartfixes: null,
  backups: null,
}))
</script>

<template>
  <main class="screen">
    <header class="head">
      <h1>{{ t('nav.health') }}</h1>
      <p class="tagline">{{ t('health.tagline') }}</p>
    </header>

    <div class="tabs">
      <button
        v-for="tab in HEALTH_TABS"
        :key="tab"
        class="tab"
        :data-active="active === tab"
        @click="router.push(`/health/${tab}`)"
      >
        {{ t(`health.tabs.${tab}`) }}
        <span v-if="badges[tab] !== null && badges[tab]! > 0" class="tab-n mono">{{
          badges[tab]
        }}</span>
      </button>
    </div>

    <component :is="TAB_COMPONENTS[active]" />
  </main>
</template>

<style scoped>
.screen {
  padding: var(--screen-padding);
  max-width: var(--content-max-width);
  margin: 0 auto;
}
.head {
  margin-bottom: 18px;
}
h1 {
  font: var(--text-h1);
  letter-spacing: -0.02em;
  margin: 0;
}
.tagline {
  color: var(--text-muted-bright);
  font-size: 14px;
  margin: 4px 0 0;
}
.tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 22px;
  border-bottom: 1px solid var(--border-subtle-2);
  padding-bottom: 14px;
  flex-wrap: wrap;
}
.tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 13px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  color: #8b97a9;
  background: transparent;
  border: 1px solid transparent;
}
.tab:hover {
  color: var(--text-secondary-bright);
}
.tab[data-active='true'] {
  color: var(--text-primary);
  background: var(--accent-tint);
  border-color: var(--accent-border);
}
.tab-n {
  font-size: var(--size-meta);
  color: var(--warning-text);
  background: var(--warning-tint);
  border: 1px solid var(--warning-border);
  border-radius: 6px;
  padding: 0 6px;
}
.mono {
  font-family: var(--font-mono);
}
</style>

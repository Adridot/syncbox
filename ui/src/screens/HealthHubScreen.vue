<script setup lang="ts">
// Santé de collection hub (SPEC-DESIGN §2/§3.4): deep-linkable tab bar
// (#/health/<tab>), badges from the canonical health selector, one frame per
// maintenance task (all "preview before write"). Tabs are lazy sub-screens.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { HEALTH_TABS, type HealthTab } from '../router'
import { useHealthStore } from '../stores/health'
import { useSettingsStore } from '../stores/settings'
import BackupsTab from './health/BackupsTab.vue'
import DuplicatesTab from './health/DuplicatesTab.vue'
import MissingFilesTab from './health/MissingFilesTab.vue'
import SmartFixesTab from './health/SmartFixesTab.vue'
import UntaggedTab from './health/UntaggedTab.vue'

const { t } = useI18n()
const router = useRouter()
const health = useHealthStore()
const settings = useSettingsStore()

const props = defineProps<{ tab?: string }>()

const activeTab = computed<HealthTab>(() =>
  HEALTH_TABS.includes(props.tab as HealthTab) ? (props.tab as HealthTab) : 'duplicates',
)

const TAB_COMPONENT = {
  duplicates: DuplicatesTab,
  missing: MissingFilesTab,
  untagged: UntaggedTab,
  smartfixes: SmartFixesTab,
  backups: BackupsTab,
}

function badge(tab: HealthTab): number | null {
  if (tab === 'duplicates') return health.badges.duplicates
  if (tab === 'untagged') return health.badges.untagged
  if (tab === 'missing') return health.missingCounts?.collection ?? null
  return null
}
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
        :data-active="activeTab === tab"
        @click="router.push(`/health/${tab}`)"
      >
        {{ t(`health.tabs.${tab}`) }}
        <span v-if="badge(tab)" class="tab-badge">{{ badge(tab) }}</span>
      </button>
    </div>

    <section v-if="!settings.configured" class="card unconfigured">
      <h3>{{ t('dashboard.unconfigured.title') }}</h3>
      <p>{{ t('dashboard.unconfigured.body') }}</p>
      <router-link to="/settings" class="btn-primary">{{ t('nav.settings') }}</router-link>
    </section>

    <component :is="TAB_COMPONENT[activeTab]" v-else :key="activeTab" />
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
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-secondary);
  padding: 7px 13px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 7px;
}
.tab:hover {
  background: var(--surface-raised);
}
.tab[data-active='true'] {
  background: var(--accent-tint);
  border-color: var(--accent-border);
  color: var(--accent-hover);
  font-weight: 500;
}
.tab-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  background: var(--warning-tint);
  border: 1px solid var(--warning-border);
  color: var(--warning-text);
  border-radius: 6px;
  padding: 1px 6px;
}
.card {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 18px;
  text-align: center;
}
.unconfigured p {
  color: var(--text-secondary);
  margin: 8px 0 16px;
}
.btn-primary {
  background: var(--accent);
  border: none;
  color: #06131f;
  padding: 9px 18px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  display: inline-block;
}
</style>

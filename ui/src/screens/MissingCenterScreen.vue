<script setup lang="ts">
// Missing tracks center (SPEC-DESIGN §2/§3.2): the unified center for all
// three scopes (library/event/collection) with a deep-link scope param
// (#/missing/<scope>). The legal path (purchase) is front and center;
// manual relink second; NO download jobs. Library/Events link here with the
// scope pre-filtered (they don't duplicate the UI). Uses the shared
// MissingList (purchase/relink/remove, ANLZ + permanent-delete via the
// global consent broker, restore D22).
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import LoadingState from '../components/LoadingState.vue'
import MissingList from '../components/MissingList.vue'
import { MISSING_SCOPES, type MissingScope } from '../router'
import { useHealthStore } from '../stores/health'
import { useMissingStore } from '../stores/missing'
import { useSettingsStore } from '../stores/settings'

const { t } = useI18n()
const router = useRouter()
const missing = useMissingStore()
const health = useHealthStore()
const settings = useSettingsStore()

const props = defineProps<{ scope?: string }>()
const loading = ref(true)

// 'all' folds the three scopes; a valid scope param filters to one.
const activeScope = computed<'all' | MissingScope>(() =>
  MISSING_SCOPES.includes(props.scope as MissingScope) ? (props.scope as MissingScope) : 'all',
)

const SCOPE_TABS: Array<'all' | MissingScope> = ['all', 'library', 'event', 'collection']

const entries = computed(() => {
  if (activeScope.value === 'all')
    return MISSING_SCOPES.flatMap((scope) => missing.byScope[scope] ?? [])
  return missing.byScope[activeScope.value] ?? []
})

watch(activeScope, load, { immediate: false })

async function load() {
  loading.value = true
  if (!settings.loaded) await settings.load()
  if (!settings.configured) {
    loading.value = false
    return
  }
  if (activeScope.value === 'all') {
    const counts = await missing.loadCounts()
    health.setMissingCounts(counts)
  } else {
    await missing.load(activeScope.value)
  }
  loading.value = false
}

function selectScope(scope: 'all' | MissingScope) {
  router.push(scope === 'all' ? '/missing' : `/missing/${scope}`)
}

// initial load
load()
</script>

<template>
  <main class="screen">
    <header class="head">
      <h1>{{ t('nav.missing') }}</h1>
      <p class="tagline">{{ t('missingCenter.tagline') }}</p>
    </header>

    <div class="scope-tabs">
      <button
        v-for="scope in SCOPE_TABS"
        :key="scope"
        class="tab"
        :data-active="activeScope === scope"
        @click="selectScope(scope)"
      >
        {{ scope === 'all' ? t('missingCenter.allScopes') : t(`scope.${scope}`) }}
      </button>
    </div>

    <section v-if="!settings.configured" class="card unconfigured">
      <h3>{{ t('dashboard.unconfigured.title') }}</h3>
      <p>{{ t('dashboard.unconfigured.body') }}</p>
      <router-link to="/settings" class="btn-primary">{{ t('nav.settings') }}</router-link>
    </section>

    <LoadingState v-else-if="loading" :rows="5" />

    <MissingList v-else :entries="entries" :show-scope="activeScope === 'all'" @changed="load" />
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
.scope-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 20px;
}
.tab {
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-secondary);
  padding: 7px 14px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
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

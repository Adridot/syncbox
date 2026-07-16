<script setup lang="ts">
// Missing tracks center (M4.10 — SPEC-DESIGN §2): ONE unified surface for
// the 3 scopes, purchase-first legal path (§6.5), deep-linkable scope param
// (#/missing/<scope>). Library/Events rows link HERE pre-filtered instead
// of duplicating the UI. Optional acquisition is shown only when the
// backend reports that the separately installed component is available.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError, NetworkError, api } from '../api/client'
import type { MissingEntry } from '../api/types'
import ErrorState from '../components/ErrorState.vue'
import LoadingState from '../components/LoadingState.vue'
import MissingEntryList from '../components/MissingEntryList.vue'
import { useRefreshOnReturn } from '../lib/refresh'
import { MISSING_SCOPES, type MissingScope } from '../router'
import { useHealthStore } from '../stores/health'

const props = defineProps<{ scope?: string }>()
const { t } = useI18n()
const router = useRouter()
const health = useHealthStore()

const TABS = ['all', ...MISSING_SCOPES] as const
type Tab = (typeof TABS)[number]

const active = computed<Tab>(() =>
  MISSING_SCOPES.includes(props.scope as MissingScope) ? (props.scope as Tab) : 'all',
)

const entriesByScope = ref<Partial<Record<MissingScope, MissingEntry[]>>>({})
const loading = ref(true)
const loadError = ref<string | null>(null)

function describe(cause: unknown): string {
  if (cause instanceof ApiError) return cause.message
  if (cause instanceof NetworkError) return t('common.networkError')
  return String(cause)
}

async function load() {
  // skeleton on FIRST load only: refreshes keep the list (and its D22 undo
  // banner) mounted — a reload must never destroy the undo affordance
  const scopes: MissingScope[] =
    active.value === 'all' ? [...MISSING_SCOPES] : [active.value as MissingScope]
  loading.value = scopes.some((scope) => entriesByScope.value[scope] === undefined)
  loadError.value = null
  try {
    const results = await Promise.all(
      scopes.map((scope) => api.get<{ entries: MissingEntry[] }>(`/api/missing/${scope}`)),
    )
    scopes.forEach((scope, index) => {
      entriesByScope.value[scope] = results[index].entries
    })
    const counts = entriesByScope.value
    if (counts.library && counts.event && counts.collection)
      health.setMissingCounts({
        library: counts.library.length,
        event: counts.event.length,
        collection: counts.collection.length,
      })
  } catch (cause) {
    loadError.value = describe(cause)
  } finally {
    loading.value = false
  }
}
// keep-alive re-entry refreshes silently (loading stays false once a scope
// is cached); the watch covers scope changes while the screen is alive
useRefreshOnReturn(() => void load())
watch(active, () => void load())

const visibleEntries = computed<MissingEntry[]>(() => {
  if (active.value === 'all')
    return MISSING_SCOPES.flatMap((scope) => entriesByScope.value[scope] ?? [])
  return entriesByScope.value[active.value as MissingScope] ?? []
})

const tabCount = (tab: Tab): number | null => {
  if (tab === 'all') {
    const all = MISSING_SCOPES.map((scope) => entriesByScope.value[scope])
    return all.every(Boolean) ? all.reduce((sum, list) => sum + list!.length, 0) : null
  }
  return entriesByScope.value[tab as MissingScope]?.length ?? null
}
</script>

<template>
  <main class="screen">
    <header class="head">
      <h1>{{ t('nav.missing') }}</h1>
      <p class="tagline">{{ t('missingCenter.tagline') }}</p>
    </header>

    <!-- legal path banner: purchase FIRST, relink for owned files (§6.5) -->
    <div class="legal">
      <span class="legal-chip">{{ t('missingCenter.recommended') }}</span>
      <div class="legal-text">
        <div class="legal-title">{{ t('missingCenter.legalTitle') }}</div>
        <div class="legal-body">{{ t('missingCenter.legalBody') }}</div>
      </div>
    </div>

    <div class="tabs">
      <button
        v-for="tab in TABS"
        :key="tab"
        class="tab"
        :data-active="active === tab"
        @click="router.push(tab === 'all' ? '/missing' : `/missing/${tab}`)"
      >
        {{ tab === 'all' ? t('missingCenter.allScopes') : t(`scope.${tab}`) }}
        <span v-if="tabCount(tab) !== null" class="tab-n mono">{{ tabCount(tab) }}</span>
      </button>
    </div>

    <LoadingState v-if="loading" :rows="5" />
    <ErrorState v-else-if="loadError" :title="t('missingCenter.loadErrorTitle')" :body="loadError">
      <button class="btn-secondary" @click="load">{{ t('common.retry') }}</button>
    </ErrorState>
    <MissingEntryList
      v-else
      :entries="visibleEntries"
      :show-scope="active === 'all'"
      @changed="load"
    />
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
.legal {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  background: linear-gradient(100deg, rgba(45, 212, 191, 0.08), rgba(77, 163, 255, 0.04));
  border: 1px solid rgba(45, 212, 191, 0.22);
  border-radius: var(--radius-card);
  padding: 14px 18px;
  margin-bottom: 18px;
}
.legal-chip {
  flex: none;
  font-size: var(--size-meta);
  font-weight: 700;
  color: var(--teal);
  background: rgba(45, 212, 191, 0.14);
  border: 1px solid var(--teal-border);
  padding: 2px 9px;
  border-radius: 6px;
  margin-top: 1px;
}
.legal-title {
  font-size: 14px;
  font-weight: 600;
}
.legal-body {
  color: #8b97a9;
  font-size: 13px;
  line-height: 1.5;
  margin-top: 2px;
}
.tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 16px;
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
  border: 1px solid var(--border-2);
}
.tab[data-active='true'] {
  color: var(--text-primary);
  background: var(--accent-tint);
  border-color: var(--accent-border);
}
.tab-n {
  font-size: var(--size-meta);
  color: var(--text-muted);
}
.tab[data-active='true'] .tab-n {
  color: var(--accent-hover);
}
.mono {
  font-family: var(--font-mono);
}
</style>

<script setup lang="ts">
// Fichiers manquants (health hub) = the COLLECTION scope of the missing
// center: snapshot rows whose file is gone on disk. Purchase / relink /
// remove (G3) via the shared list. The other scopes live in the center.
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../../api/client'
import type { MissingEntry } from '../../api/types'
import ErrorState from '../../components/ErrorState.vue'
import LoadingState from '../../components/LoadingState.vue'
import MissingEntryList from '../../components/MissingEntryList.vue'
import { useHealthStore } from '../../stores/health'

const { t } = useI18n()
const health = useHealthStore()

const entries = ref<MissingEntry[] | null>(null)
const loadError = ref<string | null>(null)

async function load() {
  loadError.value = null
  try {
    entries.value = (
      await api.get<{ entries: MissingEntry[] }>('/api/missing/collection')
    ).entries
    if (health.missingCounts)
      health.setMissingCounts({ ...health.missingCounts, collection: entries.value.length })
  } catch (cause) {
    loadError.value = cause instanceof ApiError ? cause.message : t('common.networkError')
  }
}
onMounted(() => void load())
</script>

<template>
  <div>
    <div class="intro-row">
      <p class="intro">{{ t('missing.collectionIntro') }}</p>
      <router-link class="center-link" to="/missing">{{ t('missing.openCenter') }} →</router-link>
    </div>
    <LoadingState v-if="entries === null && !loadError" :rows="4" />
    <ErrorState v-else-if="loadError" :title="t('missing.loadErrorTitle')" :body="loadError">
      <button class="btn-secondary" @click="load">{{ t('common.retry') }}</button>
    </ErrorState>
    <MissingEntryList v-else-if="entries" :entries="entries" @changed="load" />
  </div>
</template>

<style scoped>
.intro-row {
  display: flex;
  align-items: baseline;
  gap: 16px;
  margin-bottom: 14px;
}
.intro {
  flex: 1;
  font-size: 12.5px;
  color: var(--text-muted-bright);
  margin: 0;
}
.center-link {
  font-size: 12.5px;
  color: var(--accent);
  text-decoration: none;
  white-space: nowrap;
}
</style>

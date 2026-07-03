<script setup lang="ts">
// Fichiers manquants tab (SPEC-DESIGN §2): the collection scope of the
// shared MissingList — purchase/relink/remove (G3). The unified Missing
// center (M4.10) covers all three scopes; this tab is collection-only.
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import LoadingState from '../../components/LoadingState.vue'
import MissingList from '../../components/MissingList.vue'
import { useMissingStore } from '../../stores/missing'

const { t } = useI18n()
const missing = useMissingStore()
const loading = ref(true)

onMounted(reload)

async function reload() {
  loading.value = true
  await missing.load('collection')
  loading.value = false
}
</script>

<template>
  <div>
    <div class="intro">
      {{ t('missing.collectionIntro') }}
      <router-link to="/missing" class="link">{{ t('missing.openCenter') }} →</router-link>
    </div>
    <LoadingState v-if="loading" :rows="4" />
    <MissingList v-else :entries="missing.byScope.collection ?? []" @changed="reload" />
  </div>
</template>

<style scoped>
.intro {
  font-size: 12.5px;
  color: var(--text-muted-bright);
  margin-bottom: 14px;
}
.link {
  color: var(--accent);
  text-decoration: none;
  margin-left: 8px;
}
</style>

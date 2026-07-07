<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'

import AppSidebar from './components/AppSidebar.vue'
import BackendDownOverlay from './components/BackendDownOverlay.vue'
import ConsentHost from './components/ConsentHost.vue'
import OnboardingOverlay from './components/OnboardingOverlay.vue'
import RbGuardBanner from './components/RbGuardBanner.vue'
import { onboardingVisible } from './lib/onboarding'
import { useStatusStore } from './stores/status'

const status = useStatusStore()
const router = useRouter()

// ⌘, (macOS convention) opens Settings
function onKeydown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key === ',') {
    event.preventDefault()
    void router.push('/settings')
  }
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="app">
    <AppSidebar />
    <div class="main">
      <RbGuardBanner v-if="status.rbOpen" />
      <div class="content">
        <router-view />
      </div>
      <BackendDownOverlay v-if="status.backendDown" />
    </div>
    <ConsentHost />
    <OnboardingOverlay v-if="onboardingVisible" />
  </div>
</template>

<style scoped>
.app {
  display: flex;
  min-height: 100vh;
}
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  height: 100vh;
  overflow-y: auto;
  scrollbar-gutter: stable;
}
.content {
  flex: 1;
  min-width: 0;
  min-height: 0;
}
</style>

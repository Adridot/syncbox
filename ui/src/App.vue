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
    <div class="window-drag-region" data-tauri-drag-region aria-hidden="true"></div>
    <AppSidebar />
    <div class="main">
      <RbGuardBanner v-if="status.rbOpen" />
      <div class="content">
        <!-- keep-alive: EVERY screen keeps its data across navigations —
             reopening shows the last state instantly while useRefreshOnReturn
             refreshes silently (skeleton on first load only, owner 16/07) -->
        <router-view v-slot="{ Component }">
          <keep-alive>
            <component :is="Component" />
          </keep-alive>
        </router-view>
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
  height: 100vh;
  overflow: hidden;
  position: relative;
}
.window-drag-region {
  position: absolute;
  top: 0;
  right: 0;
  left: var(--traffic-light-clearance);
  height: var(--top-chrome-height);
  z-index: 1;
  -webkit-user-select: none;
  user-select: none;
}
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  height: 100vh;
  padding-top: var(--top-chrome-height);
  background: var(--bg-base);
  overflow-y: auto;
  scrollbar-gutter: stable;
}
.content {
  flex: 1;
  min-width: 0;
  min-height: 0;
}
</style>

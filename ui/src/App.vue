<script setup lang="ts">
import AppSidebar from './components/AppSidebar.vue'
import BackendDownOverlay from './components/BackendDownOverlay.vue'
import RbGuardBanner from './components/RbGuardBanner.vue'
import { useStatusStore } from './stores/status'

const status = useStatusStore()
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

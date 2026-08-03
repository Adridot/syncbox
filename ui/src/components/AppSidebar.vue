<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { useHealthStore } from '../stores/health'
import HealthPill from './HealthPill.vue'

const { t } = useI18n()
const route = useRoute()
const health = useHealthStore()

const appVersion = __APP_VERSION__

const items = computed(() => [
  { name: 'dashboard', to: '/', icon: '◎', label: t('nav.dashboard'), badge: null as number | null, warn: false },
  // ▤ : ≡ (identical-to) renders tiny in Geist next to ◎/♪ — owner 16/07
  { name: 'library', to: '/library', icon: '▤', label: t('nav.library'), badge: health.badges.library, warn: false },
  { name: 'events', to: '/events', icon: '♪', label: t('nav.events'), badge: health.badges.events, warn: false },
  { name: 'history', to: '/history', icon: '◷', label: t('nav.history'), badge: null, warn: false },
  {
    name: 'health',
    to: '/health/duplicates',
    icon: '✛',
    label: t('nav.health'),
    // health hub badge aggregates its tabs — same selector as the tabs
    badge:
      health.badges.duplicates === null && health.badges.untagged === null
        ? null
        : (health.badges.duplicates ?? 0) + (health.badges.untagged ?? 0),
    warn: true,
  },
  { name: 'missing', to: '/missing', icon: '↓', label: t('nav.missing'), badge: health.badges.missing, warn: false },
])

const isActive = (name: string) => route.name === name
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <img class="brand-mark" src="../assets/logo.png" alt="" />
      <div>
        <div class="brand-name">{{ t('app.title') }}</div>
        <div class="brand-meta">v{{ appVersion }} · macOS</div>
      </div>
    </div>

    <nav class="nav">
      <router-link
        v-for="item in items"
        :key="item.name"
        :to="item.to"
        class="nav-item"
        :data-active="isActive(item.name)"
      >
        <span class="icon">{{ item.icon }}</span>
        <span class="label">{{ item.label }}</span>
        <span
          v-if="item.badge !== null && item.badge > 0"
          class="badge"
          :data-warn="item.warn"
          >{{ item.badge }}</span
        >
      </router-link>
    </nav>

    <div class="spacer" />
    <HealthPill class="health-pill" />

    <router-link to="/settings" class="nav-item" :data-active="isActive('settings')">
      <span class="icon">⚙</span>
      <span class="label">{{ t('nav.settings') }}</span>
    </router-link>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 248px;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border-subtle-2);
  display: flex;
  flex-direction: column;
  padding: var(--top-chrome-height) 12px 14px;
  flex: none;
  height: 100vh;
  position: sticky;
  top: 0;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 8px 16px;
}
.brand-mark {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 1px solid var(--accent-border);
  object-fit: cover;
  flex: none;
}
.brand-name {
  font-weight: 600;
  font-size: 15px;
  letter-spacing: -0.01em;
}
.brand-meta {
  font-family: var(--font-mono);
  font-size: var(--size-label);
  color: var(--text-muted);
  margin-top: 1px;
}
.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 4px;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border-radius: 9px;
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 13.5px;
  cursor: pointer;
}
.nav-item:hover {
  background: var(--surface-raised);
  color: var(--text-secondary-bright);
}
.nav-item[data-active='true'] {
  background: var(--accent-tint);
  color: var(--accent-hover);
  font-weight: 500;
}
.icon {
  width: 18px;
  text-align: center;
}
.label {
  flex: 1;
}
.badge {
  font-family: var(--font-mono);
  font-size: var(--size-meta);
  background: var(--neutral-tint);
  border: 1px solid var(--neutral-border);
  color: var(--text-secondary-bright);
  border-radius: 7px;
  padding: 1px 7px;
}
.badge[data-warn='true'] {
  background: var(--warning-tint);
  border-color: var(--warning-border);
  color: var(--warning-text);
}
.spacer {
  flex: 1;
}
.health-pill {
  margin-bottom: 10px;
}
</style>

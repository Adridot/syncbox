<script setup lang="ts">
// Onboarding (M4.12 — SPEC-UNIFIED §11.4): bi-phase 10 steps (Configuration
// 4 / Prise en main 6), clickable rail, skippable, replayable from Réglages.
// Per-step CTAs wire REAL actions where cheap: Spotify connect (R1 client id
// included — first launch starts here), B3 path validation (shared
// usePathFields), and a real read-only first scan (GET /api/readouts).
// The deprecated "Module" step and the download framing do not exist.
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../api/client'
import { i18n } from '../i18n'
import { completeOnboarding } from '../lib/onboarding'
import { MACOS_DB_DEFAULT, usePathFields } from '../lib/usePathFields'
import { useSpotifyConnect } from '../lib/useSpotifyConnect'
import { useSettingsStore } from '../stores/settings'
import { useStatusStore } from '../stores/status'
import PathField from './PathField.vue'
import SpotifyClientIdHelp from './SpotifyClientIdHelp.vue'

const { t } = useI18n()
const settings = useSettingsStore()
const status = useStatusStore()
const spotify = useSpotifyConnect()

const STEPS = [
  { key: 'welcome', phase: 'setup' },
  { key: 'spotify', phase: 'setup' },
  { key: 'folders', phase: 'setup' },
  { key: 'scan', phase: 'setup' },
  { key: 'model', phase: 'tour' },
  { key: 'library', phase: 'tour' },
  { key: 'events', phase: 'tour' },
  { key: 'missing', phase: 'tour' },
  { key: 'health', phase: 'tour' },
  { key: 'apply', phase: 'tour' },
] as const

const step = ref(0)
const current = computed(() => STEPS[step.value])
const stepError = ref<string | null>(null)

const clientId = ref('')
const scanResult = ref<number | null>(null)
const scanning = ref(false)

const paths = usePathFields((text) => {
  stepError.value = text
})

onMounted(async () => {
  try {
    await paths.init() // loads settings + re-validates stored paths (B3)
    clientId.value = settings.values?.spotify_client_id ?? ''
  } catch {
    /* backend not up yet: the steps surface their own errors on action */
  }
})

function go(index: number) {
  step.value = Math.min(Math.max(index, 0), STEPS.length - 1)
  stepError.value = null
}
const next = () => go(step.value + 1)

function describe(cause: unknown): string {
  return cause instanceof ApiError ? cause.message : t('common.networkError')
}

async function saveClientId() {
  stepError.value = null
  try {
    await settings.update({ spotify_client_id: clientId.value.trim() })
  } catch (cause) {
    stepError.value = describe(cause)
  }
}

async function connectSpotify() {
  stepError.value = null
  if (clientId.value.trim() && clientId.value.trim() !== settings.values?.spotify_client_id)
    await saveClientId()
  await spotify.connect()
  if (status.spotifyConnected) next()
}

async function validatePaths() {
  stepError.value = null
  const dbOk = await paths.save('rekordbox_db_path')
  const rootOk = await paths.save('storage_root')
  if (dbOk && rootOk) next()
}

async function runFirstScan() {
  scanning.value = true
  stepError.value = null
  try {
    const readouts = await api.get<{ total_tracks: number }>('/api/readouts')
    scanResult.value = readouts.total_tracks
  } catch (cause) {
    // B1: e.g. paths not configured -> actionable, points back to Dossiers
    stepError.value = describe(cause)
  } finally {
    scanning.value = false
  }
}

async function setLang(lang: 'fr' | 'en') {
  try {
    await settings.update({ language: lang })
  } catch {
    // backend not configured yet: switch the UI locale directly
    i18n.global.locale.value = lang
    try {
      localStorage.setItem('syncbox.locale', lang)
    } catch {
      /* cache only */
    }
  }
}

function primaryAction() {
  switch (current.value.key) {
    case 'spotify':
      return connectSpotify()
    case 'folders':
      return validatePaths()
    case 'scan':
      return scanResult.value === null ? runFirstScan() : next()
    case 'apply':
      return completeOnboarding()
    default:
      return next()
  }
}

const primaryLabel = computed(() => {
  const key = current.value.key
  if (key === 'scan' && scanResult.value !== null) return t('onboarding.next')
  if (key === 'spotify' && spotify.connecting.value) return t('settings.spotify.connecting')
  if (key === 'scan' && scanning.value) return t('onboarding.scanning')
  return t(`onboarding.steps.${key}.cta`)
})
</script>

<template>
  <div class="overlay">
    <aside class="rail">
      <div class="brand">
        <div class="brand-mark">S</div>
        <span class="brand-name">Syncbox</span>
      </div>
      <template v-for="phase in ['setup', 'tour'] as const" :key="phase">
        <div class="phase-label">{{ t(`onboarding.phase.${phase}`) }}</div>
        <button
          v-for="entry in STEPS.map((s, i) => ({ ...s, i })).filter((s) => s.phase === phase)"
          :key="entry.key"
          class="rail-row"
          :data-active="entry.i === step"
          @click="go(entry.i)"
        >
          <span class="dot mono" :data-done="entry.i < step" :data-active="entry.i === step">{{
            entry.i < step ? '✓' : entry.i + 1
          }}</span>
          <span class="rail-label">{{ t(`onboarding.steps.${entry.key}.rail`) }}</span>
        </button>
      </template>
      <div class="rail-foot">
        <button class="lang" :data-active="$i18n.locale === 'fr'" @click="setLang('fr')">FR</button>
        <button class="lang" :data-active="$i18n.locale === 'en'" @click="setLang('en')">EN</button>
      </div>
    </aside>

    <section class="pane">
      <button class="skip" @click="completeOnboarding">{{ t('onboarding.skip') }}</button>

      <div class="content">
        <span class="tag">{{ t(`onboarding.steps.${current.key}.tag`) }}</span>
        <h2>{{ t(`onboarding.steps.${current.key}.title`) }}</h2>
        <p class="sub">{{ t(`onboarding.steps.${current.key}.sub`) }}</p>

        <!-- real-action blocks -->
        <div v-if="current.key === 'spotify'" class="action-block">
          <div v-if="status.spotifyConnected" class="ok-line">
            ✓ {{ t('settings.spotify.connected') }}
          </div>
          <template v-else>
            <div class="field-label">{{ t('settings.spotify.clientIdLabel') }}</div>
            <input
              v-model="clientId"
              type="text"
              class="mono client-input"
              :placeholder="t('settings.spotify.clientIdPlaceholder')"
              @blur="saveClientId"
            />
            <SpotifyClientIdHelp />
          </template>
        </div>

        <div v-else-if="current.key === 'folders'" class="action-block fields">
          <PathField
            v-model="paths.dbPath.value"
            :label="t('settings.paths.dbLabel')"
            :state="paths.state.rekordbox_db_path"
            :message="paths.message.rekordbox_db_path"
            :placeholder="MACOS_DB_DEFAULT"
            pick="file"
            @save="paths.save('rekordbox_db_path')"
          />
          <PathField
            v-model="paths.storageRoot.value"
            :label="t('settings.paths.rootLabel')"
            :state="paths.state.storage_root"
            :message="paths.message.storage_root"
            placeholder="/Volumes/DJ-SSD/Musique"
            pick="directory"
            @save="paths.save('storage_root')"
          />
        </div>

        <div v-else-if="current.key === 'scan' && scanResult !== null" class="action-block">
          <div class="ok-line">✓ {{ t('onboarding.scanDone', { n: scanResult }) }}</div>
        </div>

        <div v-if="stepError" class="error-row">{{ stepError }}</div>

        <div class="actions">
          <button v-if="step > 0" class="btn-secondary" @click="go(step - 1)">
            {{ t('onboarding.back') }}
          </button>
          <button class="btn-primary" @click="primaryAction">{{ primaryLabel }}</button>
          <button
            v-if="['spotify', 'folders', 'scan'].includes(current.key)"
            class="ghost"
            @click="next"
          >
            {{ t('onboarding.skipStep') }}
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 70;
  display: flex;
  background: var(--bg-base);
}
.rail {
  width: 232px;
  flex: none;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border-subtle-2);
  padding: 18px 14px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 8px 18px;
}
.brand-mark {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: var(--accent-tint);
  border: 1px solid var(--accent-border);
  color: var(--accent);
  font-weight: 700;
  display: grid;
  place-content: center;
}
.brand-name {
  font-weight: 600;
  font-size: 14px;
}
.phase-label {
  font-size: var(--size-label);
  text-transform: uppercase;
  letter-spacing: var(--label-tracking);
  color: var(--text-muted);
  font-weight: 600;
  padding: 12px 8px 6px;
}
.rail-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 9px;
  cursor: pointer;
  background: transparent;
  border: none;
  text-align: left;
  width: 100%;
}
.rail-row[data-active='true'] {
  background: rgba(77, 163, 255, 0.1);
}
.dot {
  width: 22px;
  height: 22px;
  flex: none;
  border-radius: 50%;
  display: grid;
  place-content: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  background: #12151d;
  border: 1px solid var(--border-2);
}
.dot[data-done='true'] {
  color: var(--teal);
  background: rgba(45, 212, 191, 0.14);
  border-color: rgba(45, 212, 191, 0.32);
}
.dot[data-active='true'] {
  color: #06131f;
  background: var(--accent);
  border-color: var(--accent);
}
.rail-label {
  font-size: 12.5px;
  color: var(--text-secondary);
}
.rail-row[data-active='true'] .rail-label {
  color: var(--text-primary);
  font-weight: 600;
}
.mono {
  font-family: var(--font-mono);
}
.rail-foot {
  margin-top: auto;
  display: flex;
  gap: 6px;
  padding: 12px 8px 0;
}
.lang {
  padding: 4px 10px;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  color: var(--text-muted-bright);
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
}
.lang[data-active='true'] {
  color: var(--accent-hover);
  background: var(--accent-tint);
  border-color: var(--accent-border);
}
.pane {
  flex: 1;
  min-width: 0;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  overflow-y: auto;
}
.skip {
  position: absolute;
  top: 20px;
  right: 24px;
  background: transparent;
  border: none;
  color: var(--text-muted-bright);
  font-size: 12.5px;
  cursor: pointer;
}
.skip:hover {
  color: var(--text-secondary-bright);
}
.content {
  max-width: 520px;
  width: 100%;
}
.tag {
  display: inline-block;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--accent);
  background: var(--accent-tint);
  border: 1px solid var(--accent-border);
  border-radius: 6px;
  padding: 2px 8px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
h2 {
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.02em;
  margin: 14px 0 0;
  line-height: 1.25;
}
.sub {
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.6;
  margin: 10px 0 0;
}
.action-block {
  margin-top: 22px;
}
.action-block.fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.ok-line {
  color: var(--success);
  font-size: 13.5px;
  font-weight: 600;
}
.field-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 5px;
}
.client-input {
  width: 100%;
  box-sizing: border-box;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 8px;
  padding: 9px 11px;
  font-size: 12px;
  color: var(--text-secondary-bright);
  outline: none;
}
.link {
  background: transparent;
  border: none;
  color: var(--accent);
  cursor: pointer;
  padding: 0;
  font-size: 12px;
}
.help-link {
  margin-top: 8px;
}
.error-row {
  margin-top: 14px;
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  border-radius: 9px;
  padding: 9px 12px;
  color: var(--danger-text);
  font-size: 12.5px;
}
.actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 26px;
}
.ghost {
  background: transparent;
  border: none;
  color: var(--text-muted-bright);
  font-size: 12.5px;
  cursor: pointer;
}
.ghost:hover {
  color: var(--text-secondary-bright);
}
</style>

<script setup lang="ts">
// Réglages (SPEC-DESIGN §2/§4): Spotify card (G1 state + authorize via
// opener), 2 editable paths with inline server validation + derived
// read-only rows, retention, language (drives vue-i18n via PUT settings),
// Avancé (G4: thresholds/weights sum==1.00 client+server, ISRC policy,
// LOCKED invariants box, reset), "Revoir l'onboarding", version footer.
// The download module + ARL card is DEPRECATED and NOT built (M4-PLAN §6).
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../api/client'
import { useCancellablePoll } from '../lib/poll-until'
import { openExternal } from '../shell'
import { useOnboardingStore } from '../stores/onboarding'
import { useSettingsStore, type MatchWeights } from '../stores/settings'
import { useStatusStore } from '../stores/status'

const { t } = useI18n()
const settings = useSettingsStore()
const status = useStatusStore()
const onboarding = useOnboardingStore()
const poll = useCancellablePoll()

const dbPath = ref('')
const storageRoot = ref('')
const pathErrors = ref<{ db?: string; storage?: string }>({})
const retention = ref(15)
const advancedOpen = ref(false)

// G4 working copy (never mutate the store until PUT succeeds)
const threshold = ref(82)
const margin = ref(6)
const weights = ref<MatchWeights>({ title: 0.52, artist: 0.36, duration: 0.12 })
const isrcPolicy = ref<'guarded' | 'trust_isrc' | 'strict'>('guarded')
const advancedError = ref<string | null>(null)

const ISRC_POLICIES = ['guarded', 'trust_isrc', 'strict'] as const

onMounted(async () => {
  if (!settings.loaded) await settings.load()
  hydrate()
})

function hydrate() {
  const v = settings.values
  if (!v) return
  dbPath.value = v.rekordbox_db_path
  storageRoot.value = v.storage_root
  retention.value = v.backup_retention
  threshold.value = v.match_confidence_threshold
  margin.value = v.match_ambiguity_margin
  weights.value = { ...v.match_weights }
  isrcPolicy.value = v.isrc_collision_policy
}

// derived read-only rows (SPEC-DESIGN §4: 2 editable + derived subdirs)
const derivedRows = computed(() => {
  if (!storageRoot.value) return []
  const base = `${storageRoot.value}/_rekordbox_sync`
  return [
    { label: t('settings.paths.inbox'), path: `${base}/inbox` },
    { label: t('settings.paths.backups'), path: `${base}/backups` },
  ]
})

async function savePath(field: 'rekordbox_db_path' | 'storage_root', value: string) {
  try {
    await settings.update({ [field]: value })
    pathErrors.value = { ...pathErrors.value, [field === 'rekordbox_db_path' ? 'db' : 'storage']: undefined }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('settings.paths.invalid')
    pathErrors.value = {
      ...pathErrors.value,
      [field === 'rekordbox_db_path' ? 'db' : 'storage']: message,
    }
  }
}

async function saveRetention() {
  await api.post('/api/doctor/retention', { backup_retention: retention.value })
}

async function setLanguage(lang: 'fr' | 'en') {
  await settings.update({ language: lang })
}

const weightsSum = computed(() =>
  Math.round((weights.value.title + weights.value.artist + weights.value.duration) * 100) / 100,
)
const weightsValid = computed(() => weightsSum.value === 1)

async function saveAdvanced() {
  advancedError.value = null
  if (!weightsValid.value) {
    advancedError.value = t('settings.advanced.sumError')
    return
  }
  try {
    await settings.update({
      match_confidence_threshold: threshold.value,
      match_ambiguity_margin: margin.value,
      match_weights: weights.value,
      isrc_collision_policy: isrcPolicy.value,
    })
  } catch (err) {
    advancedError.value = err instanceof ApiError ? err.message : t('settings.advanced.saveFailed')
  }
}

async function resetAdvanced() {
  threshold.value = 82
  margin.value = 6
  weights.value = { title: 0.52, artist: 0.36, duration: 0.12 }
  isrcPolicy.value = 'guarded'
  await saveAdvanced()
}

async function connectSpotify() {
  const { url } = await api.get<{ url: string }>('/api/spotify/authorize')
  await openExternal(url)
  await poll(() => status.spotifyConnected, () => status.refresh())
}

function replayOnboarding() {
  // "Revoir l'onboarding" relaunches at step 1 (the done-flag is re-set on
  // finish, M4-PLAN §4).
  onboarding.start()
}
</script>

<template>
  <main class="screen">
    <header class="head">
      <h1>{{ t('nav.settings') }}</h1>
    </header>

    <!-- Spotify -->
    <div class="card">
      <div class="spotify-row">
        <div class="sp-icon">♫</div>
        <div class="sp-text">
          <div class="sp-name">
            Spotify
            <span v-if="!status.spotifyConnected" class="reconnect-badge">{{
              t('settings.spotify.reconnectNeeded')
            }}</span>
          </div>
          <div class="sp-sub mono" :data-ok="status.spotifyConnected">
            {{ status.spotifyConnected ? t('settings.spotify.connected') : t('settings.spotify.disconnected') }}
          </div>
        </div>
        <button class="btn-ghost" @click="connectSpotify">
          {{ status.spotifyConnected ? t('settings.spotify.reconnect') : t('settings.spotify.connect') }}
        </button>
      </div>
    </div>

    <!-- Paths: 2 editable + derived read-only rows -->
    <div class="card">
      <div class="card-title">{{ t('settings.paths.title') }}</div>
      <div class="fields">
        <div class="field">
          <div class="field-label">{{ t('settings.paths.rekordbox') }}</div>
          <div class="path-input" :data-error="!!pathErrors.db">
            <input v-model="dbPath" class="mono" @change="savePath('rekordbox_db_path', dbPath)" />
            <span class="valid">{{ pathErrors.db ? '✕' : dbPath ? '✓' : '' }}</span>
          </div>
          <div v-if="pathErrors.db" class="field-error">{{ pathErrors.db }}</div>
        </div>
        <div class="field">
          <div class="field-label">{{ t('settings.paths.storage') }}</div>
          <div class="path-input" :data-error="!!pathErrors.storage">
            <input v-model="storageRoot" class="mono" @change="savePath('storage_root', storageRoot)" />
            <span class="valid">{{ pathErrors.storage ? '✕' : storageRoot ? '✓' : '' }}</span>
          </div>
          <div v-if="pathErrors.storage" class="field-error">{{ pathErrors.storage }}</div>
        </div>
        <div v-for="row in derivedRows" :key="row.label" class="field">
          <div class="field-label">{{ row.label }}</div>
          <div class="path-input derived">
            <span class="mono">{{ row.path }}</span>
            <span class="derived-tag">{{ t('settings.paths.derived') }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Retention + Language -->
    <div class="two-col">
      <div class="card">
        <div class="card-title">{{ t('settings.retention.title') }}</div>
        <p class="card-sub">{{ t('settings.retention.sub') }}</p>
        <div class="slider-row">
          <input v-model.number="retention" type="range" min="0" max="50" @change="saveRetention" />
          <span class="mono slider-value">{{ retention }}</span>
        </div>
      </div>
      <div class="card">
        <div class="card-title">{{ t('settings.language') }}</div>
        <div class="lang-buttons">
          <button
            class="lang-btn"
            :data-active="settings.values?.language === 'fr'"
            @click="setLanguage('fr')"
          >
            Français
          </button>
          <button
            class="lang-btn"
            :data-active="settings.values?.language === 'en'"
            @click="setLanguage('en')"
          >
            English
          </button>
        </div>
      </div>
    </div>

    <!-- Advanced (G4) -->
    <div class="card collapse">
      <div class="collapse-head" @click="advancedOpen = !advancedOpen">
        <span class="collapse-title">{{ t('settings.advanced.title') }}</span>
        <span class="chevron">{{ advancedOpen ? '▾' : '▸' }}</span>
      </div>
      <div v-if="advancedOpen" class="collapse-body">
        <div class="warn-banner">⚠ {{ t('settings.advanced.warn') }}</div>

        <div class="adv-field">
          <div class="adv-label">
            <span>{{ t('settings.advanced.threshold') }}</span>
            <span class="mono accent">{{ threshold }}</span>
          </div>
          <input v-model.number="threshold" type="range" min="60" max="100" @change="saveAdvanced" />
        </div>
        <div class="adv-field">
          <div class="adv-label">
            <span>{{ t('settings.advanced.margin') }}</span>
            <span class="mono accent">{{ margin }}</span>
          </div>
          <input v-model.number="margin" type="range" min="0" max="20" @change="saveAdvanced" />
        </div>

        <div class="adv-field">
          <div class="adv-label">
            <span>{{ t('settings.advanced.weights') }}</span>
            <span class="mono" :data-ok="weightsValid">= {{ weightsSum.toFixed(2) }}</span>
          </div>
          <div class="weights">
            <label v-for="key in (['title', 'artist', 'duration'] as const)" :key="key" class="weight">
              <span class="weight-label">{{ t(`settings.advanced.weight.${key}`) }}</span>
              <input
                v-model.number="weights[key]"
                type="number"
                step="0.01"
                min="0"
                max="1"
                class="mono"
                @change="saveAdvanced"
              />
            </label>
          </div>
        </div>

        <div class="adv-field">
          <div class="adv-label"><span>{{ t('settings.advanced.isrcPolicy') }}</span></div>
          <select v-model="isrcPolicy" class="select" @change="saveAdvanced">
            <option v-for="policy in ISRC_POLICIES" :key="policy" :value="policy">
              {{ t(`settings.advanced.policy.${policy}`) }}
            </option>
          </select>
        </div>

        <div v-if="advancedError" class="field-error">{{ advancedError }}</div>

        <div class="locked">
          <div class="locked-label">🔒 {{ t('settings.advanced.lockedLabel') }}</div>
          <div class="locked-body">{{ t('settings.advanced.lockedBody') }}</div>
        </div>

        <div class="adv-actions">
          <button class="btn-ghost" @click="resetAdvanced">{{ t('settings.advanced.reset') }}</button>
        </div>
      </div>
    </div>

    <div class="footer">
      <button class="btn-link" @click="replayOnboarding">{{ t('settings.replayOnboarding') }}</button>
      <span class="mono version">Syncbox v0.1.0</span>
    </div>
  </main>
</template>

<style scoped>
.screen {
  padding: var(--screen-padding);
  max-width: var(--content-max-width-narrow);
  margin: 0 auto;
}
.head {
  margin-bottom: 22px;
}
h1 {
  font: var(--text-h1);
  letter-spacing: -0.02em;
  margin: 0;
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 13px;
  padding: 18px;
  margin-bottom: 14px;
}
.card-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 14px;
}
.card-sub {
  font-size: 12px;
  color: var(--text-muted-bright);
  margin: 0 0 12px;
}
.spotify-row {
  display: flex;
  align-items: center;
  gap: 13px;
}
.sp-icon {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  background: var(--success-tint);
  color: var(--success);
  display: grid;
  place-content: center;
  font-size: 17px;
}
.sp-text {
  flex: 1;
}
.sp-name {
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}
.reconnect-badge {
  font-size: 10px;
  font-weight: 600;
  color: var(--warning-text);
  background: var(--warning-tint);
  border: 1px solid var(--warning-border);
  border-radius: 6px;
  padding: 2px 7px;
}
.sp-sub {
  font-size: 12px;
  color: var(--text-muted-bright);
}
.sp-sub[data-ok='true'] {
  color: var(--success);
}
.mono {
  font-family: var(--font-mono);
}
.fields {
  display: flex;
  flex-direction: column;
  gap: 11px;
}
.field-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 5px;
}
.path-input {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 8px;
  padding: 9px 11px;
}
.path-input[data-error='true'] {
  border-color: var(--danger-border);
}
.path-input input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-secondary-bright);
  font-size: 12px;
}
.path-input.derived {
  color: var(--text-muted-bright);
}
.path-input.derived .mono {
  flex: 1;
  font-size: 12px;
}
.valid {
  color: var(--success);
}
.path-input[data-error='true'] .valid {
  color: var(--danger);
}
.derived-tag {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}
.field-error {
  color: var(--danger-text);
  font-size: 11.5px;
  margin-top: 5px;
}
.two-col {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 14px;
  margin-bottom: 14px;
}
.two-col .card {
  margin-bottom: 0;
}
.slider-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.slider-row input[type='range'] {
  flex: 1;
  accent-color: var(--accent);
}
.slider-value {
  font-size: 13px;
  color: var(--text-secondary-bright);
  width: 24px;
  text-align: right;
}
.lang-buttons {
  display: flex;
  gap: 8px;
}
.lang-btn {
  flex: 1;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  color: var(--text-secondary);
  padding: 8px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
}
.lang-btn[data-active='true'] {
  background: var(--accent-tint);
  border-color: var(--accent-border);
  color: var(--accent-hover);
  font-weight: 600;
}
.collapse {
  padding: 0;
  overflow: clip;
}
.collapse-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 18px;
  cursor: pointer;
}
.collapse-title {
  font-size: 14px;
  font-weight: 600;
  flex: 1;
}
.chevron {
  font-size: 11px;
  color: var(--text-muted-bright);
}
.collapse-body {
  padding: 0 18px 18px;
}
.warn-banner {
  background: rgba(245, 181, 68, 0.06);
  border: 1px solid rgba(245, 181, 68, 0.2);
  border-radius: 9px;
  padding: 11px 13px;
  font-size: 12.5px;
  color: var(--warning-text);
  line-height: 1.5;
  margin-bottom: 16px;
}
.adv-field {
  margin-bottom: 15px;
}
.adv-label {
  display: flex;
  justify-content: space-between;
  font-size: 12.5px;
  color: var(--text-secondary-bright);
  margin-bottom: 6px;
}
.accent {
  color: var(--accent);
}
.adv-label .mono[data-ok='false'] {
  color: var(--danger-text);
}
.adv-label .mono[data-ok='true'] {
  color: var(--success);
}
.adv-field input[type='range'] {
  width: 100%;
  accent-color: var(--accent);
}
.weights {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.weight {
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 8px;
  padding: 10px;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.weight-label {
  font-size: 11px;
  color: var(--text-muted-bright);
}
.weight input {
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-secondary-bright);
  font-size: 15px;
  text-align: center;
  width: 100%;
}
.select {
  width: 100%;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 8px;
  padding: 9px 11px;
  color: var(--text-secondary-bright);
  font-family: inherit;
  font-size: 13px;
}
.locked {
  background: #0a0d13;
  border: 1px solid var(--border-subtle);
  border-radius: 9px;
  padding: 12px 13px;
  margin-top: 4px;
}
.locked-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
  margin-bottom: 8px;
}
.locked-body {
  font-size: 12px;
  color: var(--text-muted-bright);
  line-height: 1.6;
}
.adv-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 15px;
}
.btn-ghost {
  background: transparent;
  border: 1px solid var(--border-2);
  color: var(--text-secondary);
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 12.5px;
  cursor: pointer;
}
.footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 2px;
}
.btn-link {
  background: transparent;
  border: none;
  color: var(--accent);
  font-size: 13px;
  cursor: pointer;
}
.version {
  font-size: 11.5px;
  color: var(--text-muted);
}
</style>

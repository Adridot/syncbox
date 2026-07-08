<script setup lang="ts">
// Réglages (M4.11 — SPEC-DESIGN §4, SPEC-UNIFIED §5.10). Spotify card with
// the user-supplied Client ID (R1) gating the connect flow; 2 editable paths
// with SERVER-validated ticks re-checked on mount (B3 — never an optimistic
// ✓) + full inline help (R3 arbitrated 2026-07-07: 2 paths kept, NO folder
// name imposed — the protected zone is everything under <root>/rekordbox/);
// retention; language; Avancé (G4 knobs, sum=1.00, locked invariants, reset).
// The deprecated download-module card / ARL field are never built (§6.5).
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '../api/client'
import PathField from '../components/PathField.vue'
import SpotifyClientIdHelp from '../components/SpotifyClientIdHelp.vue'
import { replayOnboarding } from '../lib/onboarding'
import { MACOS_DB_DEFAULT, usePathFields } from '../lib/usePathFields'
import { useSpotifyConnect } from '../lib/useSpotifyConnect'
import { type MatchWeights, useSettingsStore } from '../stores/settings'
import { useStatusStore } from '../stores/status'

const { t } = useI18n()
const settings = useSettingsStore()
const status = useStatusStore()
const spotify = useSpotifyConnect()

const appVersion = __APP_VERSION__

const DEFAULTS = {
  match_confidence_threshold: 82,
  match_ambiguity_margin: 6,
  match_weights: { title: 0.52, artist: 0.36, duration: 0.12 },
  isrc_collision_policy: 'guarded' as const,
}

const clientId = ref('')
const retention = ref(15)
const language = ref('fr')
const threshold = ref(82)
const margin = ref(6)
const weights = reactive<MatchWeights>({ ...DEFAULTS.match_weights })
const isrcPolicy = ref<string>('guarded')

const banner = ref<{ tone: 'error' | 'success'; text: string } | null>(null)
const connectAttempted = ref(false)

function describe(cause: unknown): string {
  return cause instanceof ApiError ? cause.message : t('common.networkError')
}

// B3 lives in ONE place: usePathFields (init re-validates the stored paths)
const paths = usePathFields((text) => {
  banner.value = { tone: 'error', text }
})
const { dbPath, storageRoot } = paths

onMounted(async () => {
  try {
    await paths.init()
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
    return
  }
  const values = settings.values!
  clientId.value = values.spotify_client_id
  retention.value = values.backup_retention
  language.value = values.language
  threshold.value = values.match_confidence_threshold
  margin.value = values.match_ambiguity_margin
  Object.assign(weights, values.match_weights)
  isrcPolicy.value = values.isrc_collision_policy
})

async function saveSetting(partial: Record<string, unknown>, success?: string) {
  banner.value = null
  try {
    await settings.update(partial)
    if (success) banner.value = { tone: 'success', text: success }
    return true
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
    return false
  }
}

const saveClientId = () =>
  saveSetting({ spotify_client_id: clientId.value.trim() }, t('settings.spotify.clientIdSaved'))

async function connect() {
  connectAttempted.value = false
  await spotify.connect()
  connectAttempted.value = true
}
const connectFailed = computed(
  () => connectAttempted.value && !status.spotifyConnected && !spotify.connecting.value,
)

const weightsSum = computed(() =>
  Math.round((weights.title + weights.artist + weights.duration) * 100) / 100,
)
const weightsValid = computed(() => weightsSum.value === 1)

const saveAdvanced = () =>
  saveSetting(
    {
      match_confidence_threshold: Number(threshold.value),
      match_ambiguity_margin: Number(margin.value),
      match_weights: { title: weights.title, artist: weights.artist, duration: weights.duration },
      isrc_collision_policy: isrcPolicy.value,
    },
    t('settings.advanced.saved'),
  )

async function resetAdvanced() {
  if (await saveSetting({ ...DEFAULTS }, t('settings.advanced.resetDone'))) {
    threshold.value = DEFAULTS.match_confidence_threshold
    margin.value = DEFAULTS.match_ambiguity_margin
    Object.assign(weights, DEFAULTS.match_weights)
    isrcPolicy.value = DEFAULTS.isrc_collision_policy
  }
}

const setLanguage = (lang: 'fr' | 'en') => {
  language.value = lang
  void saveSetting({ language: lang })
}

const derivedRows = computed(() => {
  const root = settings.values?.storage_root
  if (!root) return []
  return ['protected', 'inbox', 'events', 'backups'].map((key) => ({
    key,
    path: key === 'protected' ? `${root}/rekordbox/` : `${root}/_syncbox/${key}`,
    label: t(`settings.paths.derived.${key}`),
    desc: t(`settings.paths.derived.${key}Desc`),
  }))
})
</script>

<template>
  <main class="screen">
    <header class="head">
      <h1>{{ t('nav.settings') }}</h1>
    </header>

    <div v-if="banner" class="banner" :data-tone="banner.tone" role="status">
      <span class="banner-text">{{ banner.text }}</span>
      <button class="banner-close" @click="banner = null">✕</button>
    </div>

    <!-- Spotify (R1: user-supplied Client ID) -->
    <section class="card">
      <div class="spotify-row">
        <div class="spotify-icon">♫</div>
        <div class="spotify-text">
          <div class="spotify-title">
            Spotify
            <span v-if="connectFailed" class="fail-chip">{{
              t('settings.spotify.failed')
            }}</span>
          </div>
          <div class="spotify-sub mono" :data-ok="status.spotifyConnected">
            {{
              status.spotifyConnected
                ? t('settings.spotify.connected')
                : t('settings.spotify.notConnected')
            }}
          </div>
        </div>
        <button
          class="btn-primary"
          :disabled="!settings.values?.spotify_client_id || spotify.connecting.value"
          :title="
            !settings.values?.spotify_client_id ? t('settings.spotify.needClientId') : undefined
          "
          @click="connect"
        >
          {{
            spotify.connecting.value
              ? t('settings.spotify.connecting')
              : status.spotifyConnected
                ? t('settings.spotify.reconnect')
                : t('settings.spotify.connect')
          }}
        </button>
      </div>
      <div v-if="spotify.error.value" class="inline-error">{{ spotify.error.value }}</div>
      <div v-if="!settings.values?.spotify_client_id" class="gate-note">
        {{ t('settings.spotify.needClientId') }}
      </div>

      <div class="client-id">
        <div class="field-label">{{ t('settings.spotify.clientIdLabel') }}</div>
        <div class="client-id-row">
          <input
            v-model="clientId"
            type="text"
            class="mono"
            :placeholder="t('settings.spotify.clientIdPlaceholder')"
            @keydown.enter.prevent="saveClientId"
          />
          <button class="btn-secondary small" @click="saveClientId">
            {{ t('settings.paths.validate') }}
          </button>
        </div>
        <SpotifyClientIdHelp />
      </div>
    </section>

    <!-- Paths (2 editable + derived read-only rows; R3 help; B3 ticks) -->
    <section class="card">
      <h3>{{ t('settings.paths.title') }}</h3>
      <div class="paths">
        <PathField
          v-model="dbPath"
          :label="t('settings.paths.dbLabel')"
          :state="paths.state.rekordbox_db_path"
          :message="paths.message.rekordbox_db_path"
          :placeholder="MACOS_DB_DEFAULT"
          pick="file"
          @save="paths.save('rekordbox_db_path')"
        >
          {{ t('settings.paths.dbHelp') }}
          <button v-if="!dbPath" class="link" @click="dbPath = MACOS_DB_DEFAULT">
            {{ t('settings.paths.useMacDefault') }}
          </button>
          <details class="help-details">
            <summary>{{ t('settings.paths.dbFindTitle') }}</summary>
            <p>{{ t('settings.paths.dbFindBody') }}</p>
          </details>
        </PathField>
        <PathField
          v-model="storageRoot"
          :label="t('settings.paths.rootLabel')"
          :state="paths.state.storage_root"
          :message="paths.message.storage_root"
          placeholder="/Volumes/DJ-SSD/Musique"
          pick="directory"
          @save="paths.save('storage_root')"
        >
          {{ t('settings.paths.rootHelp') }}
        </PathField>
      </div>

      <div v-if="derivedRows.length" class="derived">
        <div class="derived-title">{{ t('settings.paths.derivedTitle') }}</div>
        <div v-for="row in derivedRows" :key="row.key" class="derived-row">
          <div class="derived-head">
            <span class="derived-label">{{ row.label }}</span>
            <span class="derived-path mono">{{ row.path }}</span>
          </div>
          <div class="derived-desc">{{ row.desc }}</div>
        </div>
        <div class="derived-note">{{ t('settings.paths.derivedNote') }}</div>
      </div>
    </section>

    <!-- Retention + language -->
    <div class="two-cols">
      <section class="card">
        <h3>{{ t('settings.retention.title') }}</h3>
        <p class="card-sub">{{ t('settings.retention.sub') }}</p>
        <div class="retention-row">
          <input
            v-model.number="retention"
            type="range"
            min="0"
            max="50"
            @change="saveSetting({ backup_retention: Number(retention) })"
          />
          <span class="mono retention-value">{{ retention }}</span>
        </div>
      </section>
      <section class="card">
        <h3>{{ t('settings.language.title') }}</h3>
        <div class="lang-row">
          <button class="lang" :data-active="language === 'fr'" @click="setLanguage('fr')">
            Français
          </button>
          <button class="lang" :data-active="language === 'en'" @click="setLanguage('en')">
            English
          </button>
        </div>
      </section>
    </div>

    <!-- Avancé (G4) — collapsed, guard-railed -->
    <section class="card advanced">
      <details>
        <summary class="advanced-summary">{{ t('settings.advanced.title') }}</summary>
        <div class="advanced-body">
          <div class="advanced-warning">⚠ {{ t('settings.advanced.warning') }}</div>

          <div class="knob">
            <div class="knob-head">
              <span>{{ t('settings.advanced.threshold') }}</span>
              <span class="mono accent">{{ threshold }}</span>
            </div>
            <input v-model.number="threshold" type="range" min="60" max="100" />
          </div>
          <div class="knob">
            <div class="knob-head">
              <span>{{ t('settings.advanced.margin') }}</span>
              <span class="mono accent">{{ margin }}</span>
            </div>
            <input v-model.number="margin" type="range" min="0" max="20" />
          </div>

          <div class="knob">
            <div class="knob-head">
              <span>{{ t('settings.advanced.weights') }}</span>
              <span class="mono" :class="weightsValid ? 'sum-ok' : 'sum-bad'"
                >= {{ weightsSum.toFixed(2) }}</span
              >
            </div>
            <div class="weights">
              <label
                v-for="key in ['title', 'artist', 'duration'] as const"
                :key="key"
                class="weight"
              >
                <span class="weight-label">{{ t(`settings.advanced.weight_${key}`) }}</span>
                <input
                  v-model.number="weights[key]"
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  class="mono"
                />
              </label>
            </div>
            <div v-if="!weightsValid" class="inline-error">
              {{ t('settings.advanced.sumError') }}
            </div>
          </div>

          <div class="knob">
            <div class="knob-head">
              <span>{{ t('settings.advanced.isrcPolicy') }}</span>
            </div>
            <select v-model="isrcPolicy">
              <option value="guarded">{{ t('settings.advanced.isrc_guarded') }}</option>
              <option value="trust_isrc">{{ t('settings.advanced.isrc_trust') }}</option>
              <option value="strict">{{ t('settings.advanced.isrc_strict') }}</option>
            </select>
          </div>

          <div class="locked">
            <div class="locked-title">🔒 {{ t('settings.advanced.lockedTitle') }}</div>
            <div class="locked-body">{{ t('settings.advanced.lockedBody') }}</div>
          </div>

          <div class="advanced-actions">
            <button class="btn-secondary" @click="resetAdvanced">
              {{ t('settings.advanced.reset') }}
            </button>
            <button class="btn-primary" :disabled="!weightsValid" @click="saveAdvanced">
              {{ t('settings.advanced.save') }}
            </button>
          </div>
        </div>
      </details>
    </section>

    <footer class="foot">
      <button class="link foot-link" @click="replayOnboarding">
        {{ t('settings.replayOnboarding') }}
      </button>
      <span class="version mono">Syncbox v{{ appVersion }}</span>
    </footer>
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
.banner {
  display: flex;
  align-items: center;
  gap: 10px;
  border-radius: 9px;
  padding: 9px 12px;
  margin-bottom: 12px;
  font-size: 12.5px;
}
.banner[data-tone='error'] {
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  color: var(--danger-text);
}
.banner[data-tone='success'] {
  background: var(--success-tint);
  border: 1px solid var(--success-border);
  color: var(--success);
}
.banner-text {
  flex: 1;
}
.banner-close {
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 18px;
  margin-bottom: 14px;
}
.card h3 {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 14px;
}
.card-sub {
  font-size: 12px;
  color: var(--text-muted-bright);
  margin: -8px 0 12px;
}
.spotify-row {
  display: flex;
  align-items: center;
  gap: 13px;
}
.spotify-icon {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  background: var(--success-tint);
  display: grid;
  place-content: center;
  color: var(--success);
  font-size: 17px;
}
.spotify-text {
  flex: 1;
  min-width: 0;
}
.spotify-title {
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}
.fail-chip {
  font-size: var(--size-label);
  font-weight: 600;
  color: var(--warning-text);
  background: var(--warning-tint);
  border: 1px solid var(--warning-border);
  border-radius: 6px;
  padding: 2px 7px;
}
.spotify-sub {
  font-size: 12px;
  color: var(--text-muted-bright);
  margin-top: 2px;
}
.spotify-sub[data-ok='true'] {
  color: var(--success);
}
.inline-error {
  font-size: 12px;
  color: var(--danger-text);
  margin-top: 9px;
}
.gate-note {
  font-size: 12px;
  color: var(--warning-text);
  margin-top: 9px;
}
.client-id {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border-subtle-2);
}
.field-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 5px;
}
.client-id-row {
  display: flex;
  gap: 8px;
}
.client-id-row input {
  flex: 1;
  min-width: 0;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 8px;
  padding: 9px 11px;
  font-size: 12px;
  color: var(--text-secondary-bright);
  outline: none;
}
.mono {
  font-family: var(--font-mono);
}
.btn-secondary.small {
  padding: 7px 12px;
  font-size: 12px;
  flex: none;
}
.help-details {
  margin-top: 8px;
}
.help-details summary {
  font-size: 12px;
  color: var(--accent);
  cursor: pointer;
}
.help-details p,
.help-steps {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 8px 0 0;
}
.help-steps {
  padding-left: 18px;
}
.redirect {
  color: var(--accent-hover);
  background: var(--surface-raised);
  border-radius: 5px;
  padding: 1px 5px;
}
.link {
  background: transparent;
  border: none;
  color: var(--accent);
  font-size: inherit;
  cursor: pointer;
  padding: 0;
  font-family: inherit;
}
.paths {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.derived {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--border-subtle-2);
}
.derived-title {
  font-size: var(--size-label);
  text-transform: uppercase;
  letter-spacing: var(--label-tracking);
  color: var(--text-muted);
  font-weight: 600;
  margin-bottom: 9px;
}
.derived-row {
  padding: 7px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.derived-row:last-of-type {
  border-bottom: none;
}
.derived-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
.derived-label {
  flex: none;
  min-width: 160px;
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 600;
}
.derived-path {
  font-size: 11.5px;
  color: var(--text-muted-bright);
  min-width: 0;
  word-break: break-all; /* the full path always reads, however narrow */
  user-select: text;
}
.derived-desc {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 3px;
  line-height: 1.5;
}
.derived-note {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 9px;
  line-height: 1.5;
}
.two-cols {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 14px;
}
.two-cols .card {
  margin-bottom: 0;
}
.retention-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.retention-row input {
  flex: 1;
  accent-color: var(--accent);
}
.retention-value {
  font-size: 13px;
  color: var(--text-secondary-bright);
  width: 24px;
  text-align: right;
}
.lang-row {
  display: flex;
  gap: 8px;
}
.lang {
  padding: 7px 14px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 600;
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
.advanced {
  padding: 0;
}
.advanced-summary {
  font-size: 14px;
  font-weight: 600;
  padding: 16px 18px;
  cursor: pointer;
}
.advanced-body {
  padding: 0 18px 18px;
  display: flex;
  flex-direction: column;
  gap: 15px;
}
.advanced-warning {
  background: rgba(245, 181, 68, 0.06);
  border: 1px solid rgba(245, 181, 68, 0.2);
  border-radius: 9px;
  padding: 11px 13px;
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.knob-head {
  display: flex;
  justify-content: space-between;
  font-size: 12.5px;
  margin-bottom: 6px;
  color: var(--text-secondary-bright);
}
.knob input[type='range'] {
  width: 100%;
  accent-color: var(--accent);
}
.accent {
  color: var(--accent);
}
.sum-ok {
  color: var(--success);
}
.sum-bad {
  color: var(--danger-text);
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
  display: block;
}
.weight-label {
  display: block;
  font-size: var(--size-meta);
  color: var(--text-muted-bright);
  margin-bottom: 3px;
}
.weight input {
  width: 100%;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-secondary-bright);
  font-size: 15px;
  text-align: center;
}
.knob select {
  width: 100%;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 8px;
  padding: 9px 11px;
  color: var(--text-secondary-bright);
  font: inherit;
  font-size: 13px;
}
.locked {
  background: #0a0d13;
  border: 1px solid #161b26;
  border-radius: 9px;
  padding: 12px 13px;
}
.locked-title {
  font-size: var(--size-label);
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
.advanced-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 2px;
}
.foot-link {
  font-size: 13px;
}
.version {
  font-size: 11.5px;
  color: var(--text-muted);
}
</style>

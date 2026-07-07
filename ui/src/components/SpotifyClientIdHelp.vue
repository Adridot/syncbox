<script setup lang="ts">
// The full "create your Spotify app" walkthrough — ONE definition, used by
// Réglages and the onboarding Spotify step. The redirect URI shown here is
// the sidecar's hardcoded constant (spotify.py REDIRECT_URI): Spotify
// refuses the whole flow ("redirect_uri: Not matching configuration") unless
// the dashboard carries this EXACT string, so it is copyable verbatim.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { openExternal } from '../shell'

const REDIRECT_URI = 'http://127.0.0.1:8765/callback'
const { t } = useI18n()
const copied = ref(false)

async function copy() {
  try {
    await navigator.clipboard.writeText(REDIRECT_URI)
  } catch {
    // WKWebView without clipboard permission: legacy path
    const area = document.createElement('textarea')
    area.value = REDIRECT_URI
    document.body.appendChild(area)
    area.select()
    document.execCommand('copy')
    area.remove()
  }
  copied.value = true
  window.setTimeout(() => (copied.value = false), 2000)
}
</script>

<template>
  <details class="help-details">
    <summary>{{ t('settings.spotify.clientIdHelpTitle') }}</summary>
    <p class="intro">{{ t('settings.spotify.helpIntro') }}</p>
    <ol class="steps">
      <li>
        <button class="link" @click="openExternal('https://developer.spotify.com/dashboard')">
          {{ t('settings.spotify.helpStep1') }} ↗
        </button>
      </li>
      <li>{{ t('settings.spotify.helpStep2') }}</li>
      <li>
        {{ t('settings.spotify.helpStep3') }}
        <div class="redirect-row">
          <code class="redirect mono">{{ REDIRECT_URI }}</code>
          <button class="btn-secondary copy" @click="copy">
            {{ copied ? t('settings.spotify.copied') : t('settings.spotify.copy') }}
          </button>
        </div>
        <div class="warn">{{ t('settings.spotify.helpStep3warn') }}</div>
      </li>
      <li>{{ t('settings.spotify.helpStep4') }}</li>
      <li>{{ t('settings.spotify.helpStep5') }}</li>
    </ol>
    <p class="hint">{{ t('settings.spotify.redirectErrorHint') }}</p>
  </details>
</template>

<style scoped>
.help-details {
  margin-top: 8px;
}
.help-details summary {
  font-size: 12px;
  color: var(--accent);
  cursor: pointer;
}
.intro {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 8px 0 0;
}
.steps {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin: 8px 0 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.redirect-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 5px;
  flex-wrap: wrap;
}
.redirect {
  color: var(--accent-hover);
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 12px;
  user-select: all;
  word-break: break-all;
}
.mono {
  font-family: var(--font-mono);
}
.copy {
  padding: 4px 10px;
  font-size: 11.5px;
  flex: none;
}
.warn {
  color: var(--warning-text);
  font-size: 11.5px;
  margin-top: 4px;
}
.hint {
  font-size: 11.5px;
  color: var(--text-muted);
  line-height: 1.6;
  margin: 10px 0 0;
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
</style>

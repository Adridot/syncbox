<script setup lang="ts">
// Onboarding overlay (SPEC-DESIGN §2, SPEC-UNIFIED §11.4): full-screen,
// clickable 2-phase rail, skippable, per-step CTAs wiring real actions where
// cheap (Spotify connect, paths, first scan), FR/EN toggle present from the
// onboarding. Done-flag in localStorage. Replayable from Settings.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { api } from '../api/client'
import { useCancellablePoll } from '../lib/poll-until'
import { openExternal } from '../shell'
import { ONBOARDING_STEPS, useOnboardingStore } from '../stores/onboarding'
import { useSettingsStore } from '../stores/settings'
import { useStatusStore } from '../stores/status'

const { t, locale } = useI18n()
const router = useRouter()
const onboarding = useOnboardingStore()
const settings = useSettingsStore()
const status = useStatusStore()
const poll = useCancellablePoll()

const busy = ref(false)

const stepKey = computed(() => onboarding.step.key)
const phaseSteps = computed(() => ({
  setup: ONBOARDING_STEPS.filter((s) => s.phase === 'setup'),
  tour: ONBOARDING_STEPS.filter((s) => s.phase === 'tour'),
}))

// tag e.g. "Configuration · 1 / 4" / "Prise en main · Le principe"
const tag = computed(() => {
  const step = onboarding.step
  if (step.phase === 'setup') {
    const n = phaseSteps.value.setup.indexOf(step) + 1
    if (step.key === 'welcome') return t('onboarding.phase.welcome')
    return `${t('onboarding.phase.setup')} · ${n} / ${onboarding.setupCount}`
  }
  return `${t('onboarding.phase.tour')} · ${t(`onboarding.steps.${step.key}.sub_tag`)}`
})

async function runAction() {
  const action = onboarding.step.action
  if (!action) return onboarding.next()
  busy.value = true
  try {
    if (action === 'spotify') {
      const { url } = await api.get<{ url: string }>('/api/spotify/authorize')
      await openExternal(url)
      await poll(() => status.spotifyConnected, () => status.refresh(), { attempts: 30 })
    } else if (action === 'paths') {
      // cheap wiring: jump to Settings to fill the 2 paths, then come back
      router.push('/settings')
    } else if (action === 'scan') {
      if (settings.configured) await api.post('/api/sources/sync').catch(() => {})
    }
  } finally {
    busy.value = false
    onboarding.next()
  }
}

async function setLocale(lang: 'fr' | 'en') {
  locale.value = lang
  if (settings.loaded) await settings.update({ language: lang }).catch(() => {})
}
</script>

<template>
  <div class="overlay">
    <aside class="rail">
      <div class="rail-brand">Syncbox</div>
      <div class="rail-phase">{{ t('onboarding.phase.setup') }}</div>
      <button
        v-for="step in phaseSteps.setup"
        :key="step.key"
        class="rail-item"
        :data-active="stepKey === step.key"
        :data-done="ONBOARDING_STEPS.indexOf(step) < onboarding.index"
        @click="onboarding.goto(ONBOARDING_STEPS.indexOf(step))"
      >
        {{ t(`onboarding.steps.${step.key}.rail`) }}
      </button>
      <div class="rail-phase">{{ t('onboarding.phase.tour') }}</div>
      <button
        v-for="step in phaseSteps.tour"
        :key="step.key"
        class="rail-item"
        :data-active="stepKey === step.key"
        :data-done="ONBOARDING_STEPS.indexOf(step) < onboarding.index"
        @click="onboarding.goto(ONBOARDING_STEPS.indexOf(step))"
      >
        {{ t(`onboarding.steps.${step.key}.rail`) }}
      </button>
      <div class="rail-foot">
        <div class="lang">
          <button :data-active="locale === 'fr'" @click="setLocale('fr')">FR</button>
          <button :data-active="locale === 'en'" @click="setLocale('en')">EN</button>
        </div>
      </div>
    </aside>

    <main class="stage">
      <button class="skip" @click="onboarding.finish()">{{ t('onboarding.skip') }} ✕</button>
      <div class="stage-inner">
        <div class="step-tag">{{ tag }}</div>
        <h2>{{ t(`onboarding.steps.${stepKey}.title`) }}</h2>
        <p class="step-sub">{{ t(`onboarding.steps.${stepKey}.sub`) }}</p>

        <div class="dots">
          <span
            v-for="(step, i) in ONBOARDING_STEPS"
            :key="step.key"
            class="dot"
            :data-active="i === onboarding.index"
            :data-done="i < onboarding.index"
          />
        </div>

        <div class="cta-row">
          <button v-if="onboarding.index > 0" class="btn-ghost" @click="onboarding.goto(onboarding.index - 1)">
            {{ t('onboarding.back') }}
          </button>
          <button class="btn-primary" :disabled="busy" @click="runAction">
            {{ busy ? t('onboarding.working') : t(`onboarding.steps.${stepKey}.cta`) }}
          </button>
        </div>
      </div>
    </main>
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
  width: 240px;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border-subtle-2);
  padding: 20px 14px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.rail-brand {
  font-weight: 600;
  font-size: 15px;
  padding: 0 8px 16px;
}
.rail-phase {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.09em;
  color: var(--text-muted);
  font-weight: 600;
  padding: 14px 8px 7px;
}
.rail-item {
  text-align: left;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
}
.rail-item:hover {
  background: var(--surface-raised);
}
.rail-item[data-active='true'] {
  background: var(--accent-tint);
  color: var(--accent-hover);
  font-weight: 500;
}
.rail-item[data-done='true']:not([data-active='true']) {
  color: var(--success);
}
.rail-foot {
  margin-top: auto;
}
.lang {
  display: flex;
  gap: 6px;
  padding: 8px;
}
.lang button {
  flex: 1;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  color: var(--text-secondary);
  padding: 6px;
  border-radius: 7px;
  font-size: 12px;
  cursor: pointer;
}
.lang button[data-active='true'] {
  background: var(--accent-tint);
  border-color: var(--accent-border);
  color: var(--accent-hover);
}
.stage {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.skip {
  position: absolute;
  top: 24px;
  right: 28px;
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: 13px;
  cursor: pointer;
}
.stage-inner {
  max-width: 580px;
}
.step-tag {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--accent);
  font-weight: 600;
}
h2 {
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.02em;
  margin: 8px 0 0;
}
.step-sub {
  color: var(--text-secondary);
  font-size: 13.5px;
  margin-top: 9px;
  line-height: 1.6;
}
.dots {
  display: flex;
  gap: 7px;
  margin-top: 26px;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
}
.dot[data-active='true'] {
  background: var(--accent);
  border-color: var(--accent);
}
.dot[data-done='true'] {
  background: var(--success);
  border-color: var(--success);
}
.cta-row {
  display: flex;
  gap: 12px;
  margin-top: 26px;
}
.btn-ghost {
  background: transparent;
  border: 1px solid var(--border-2);
  color: var(--text-secondary);
  padding: 10px 20px;
  border-radius: 10px;
  font-size: 13.5px;
  cursor: pointer;
}
.btn-primary {
  background: var(--accent);
  border: none;
  color: #06131f;
  padding: 10px 24px;
  border-radius: 10px;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
}
.btn-primary:disabled {
  opacity: 0.6;
  cursor: default;
}
</style>

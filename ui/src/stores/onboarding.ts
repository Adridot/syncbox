/* Onboarding state (SPEC-UNIFIED §11.4): bi-phase 10-step flow —
   Configuration (4: welcome/Spotify/folders/scan) + Prise en main (6: model/
   library/events/missing/health/apply). The mockup's "Module" step and the
   "Acquisition" naming are removed (download scope dropped, M4-PLAN §0/§6).
   The done-flag lives in localStorage (NOT a sidecar setting). */

import { defineStore } from 'pinia'

export const ONBOARDING_DONE_KEY = 'syncbox.onboarding-done'

export interface OnboardingStep {
  key: string
  phase: 'setup' | 'tour'
  /** a real action this step can trigger (Spotify connect, first sync) */
  action?: 'spotify' | 'paths' | 'scan'
}

// 10 steps, in order. Copy lives in i18n under onboarding.steps.<key>.
export const ONBOARDING_STEPS: OnboardingStep[] = [
  { key: 'welcome', phase: 'setup' },
  { key: 'spotify', phase: 'setup', action: 'spotify' },
  { key: 'folders', phase: 'setup', action: 'paths' },
  { key: 'scan', phase: 'setup', action: 'scan' },
  { key: 'model', phase: 'tour' },
  { key: 'library', phase: 'tour' },
  { key: 'events', phase: 'tour' },
  { key: 'missing', phase: 'tour' },
  { key: 'health', phase: 'tour' },
  { key: 'apply', phase: 'tour' },
]

export const useOnboardingStore = defineStore('onboarding', {
  state: () => ({
    active: false,
    index: 0,
  }),
  getters: {
    step: (state) => ONBOARDING_STEPS[state.index],
    isLast: (state) => state.index === ONBOARDING_STEPS.length - 1,
    total: () => ONBOARDING_STEPS.length,
    setupCount: () => ONBOARDING_STEPS.filter((s) => s.phase === 'setup').length,
  },
  actions: {
    /** Show onboarding on first launch (done-flag absent). */
    maybeStart() {
      try {
        if (localStorage.getItem(ONBOARDING_DONE_KEY) !== '1') this.start()
      } catch {
        /* storage unavailable: skip onboarding */
      }
    },
    start() {
      this.active = true
      this.index = 0
    },
    goto(index: number) {
      if (index >= 0 && index < ONBOARDING_STEPS.length) this.index = index
    },
    next() {
      if (this.isLast) this.finish()
      else this.index += 1
    },
    finish() {
      this.active = false
      try {
        localStorage.setItem(ONBOARDING_DONE_KEY, '1')
      } catch {
        /* best-effort */
      }
    },
  },
})

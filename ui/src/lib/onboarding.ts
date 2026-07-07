/* Onboarding visibility (M4-PLAN §4): done-flag in localStorage — NOT a
   sidecar setting. "Revoir l'onboarding" relaunches at step 1. */

import { ref } from 'vue'

const KEY = 'syncbox.onboarding-done'

function readDone(): boolean {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return true // storage unavailable: never trap the user in the overlay
  }
}

export const onboardingVisible = ref(!readDone())

export function completeOnboarding(): void {
  try {
    localStorage.setItem(KEY, '1')
  } catch {
    /* best-effort */
  }
  onboardingVisible.value = false
}

export function replayOnboarding(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* best-effort */
  }
  onboardingVisible.value = true
}

/* Settings store: GET/PUT /api/settings. settings.language is the single
   source of truth for the vue-i18n locale — localStorage only caches the
   last known value for pre-settings boot (M4-PLAN §4). Most endpoints 400
   until both paths are set: `configured` gates the data screens. */

import { defineStore } from 'pinia'

import { NetworkError, api } from '../api/client'
import { i18n } from '../i18n'

export const SETTINGS_LOAD_ATTEMPTS = 15
export const SETTINGS_RETRY_MS = 800

export interface MatchWeights {
  title: number
  artist: number
  duration: number
}

export interface SettingsPayload {
  spotify_client_id: string
  rekordbox_db_path: string
  storage_root: string
  backup_retention: number
  language: string
  match_confidence_threshold: number
  match_ambiguity_margin: number
  match_weights: MatchWeights
  isrc_collision_policy: 'guarded' | 'trust_isrc' | 'strict'
}

function applyLocale(language: string): void {
  if (language === 'en' || language === 'fr') {
    i18n.global.locale.value = language
    try {
      localStorage.setItem('syncbox.locale', language)
    } catch {
      /* cache only */
    }
  }
}

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    values: null as SettingsPayload | null,
    loaded: false,
  }),
  getters: {
    configured: (state) =>
      Boolean(state.values?.rekordbox_db_path && state.values?.storage_root),
  },
  actions: {
    async load() {
      for (let attempt = 1; attempt <= SETTINGS_LOAD_ATTEMPTS; attempt += 1) {
        try {
          this.values = await api.get<SettingsPayload>('/api/settings')
          this.loaded = true
          applyLocale(this.values.language)
          return
        } catch (error) {
          if (!(error instanceof NetworkError) || attempt === SETTINGS_LOAD_ATTEMPTS) throw error
          await new Promise((resolve) => setTimeout(resolve, SETTINGS_RETRY_MS))
        }
      }
    },
    async update(partial: Partial<SettingsPayload>) {
      this.values = await api.put<SettingsPayload>('/api/settings', partial)
      applyLocale(this.values.language)
      return this.values
    },
  },
})

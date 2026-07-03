/* Settings store: GET/PUT /api/settings. settings.language is the single
   source of truth for the vue-i18n locale — localStorage only caches the
   last known value for pre-settings boot (M4-PLAN §4). Most endpoints 400
   until both paths are set: `configured` gates the data screens. */

import { defineStore } from 'pinia'

import { api } from '../api/client'
import { i18n } from '../i18n'

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
      this.values = await api.get<SettingsPayload>('/api/settings')
      this.loaded = true
      applyLocale(this.values.language)
    },
    async update(partial: Partial<SettingsPayload>) {
      this.values = await api.put<SettingsPayload>('/api/settings', partial)
      applyLocale(this.values.language)
      return this.values
    },
  },
})

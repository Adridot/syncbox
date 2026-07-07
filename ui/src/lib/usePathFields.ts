/* ONE definition of the B3 path-validation rule, shared by Réglages and the
   onboarding "Dossiers" step: a ✓ appears only after the SERVER validated
   the path (PUT /api/settings runs validate_directory / file checks), and
   stored paths are re-validated on init — the tick is never optimistic. */

import { reactive, ref } from 'vue'

import { ApiError } from '../api/client'
import type { PathState } from '../components/PathField.vue'
import { useSettingsStore } from '../stores/settings'

export type PathKey = 'rekordbox_db_path' | 'storage_root'

export const MACOS_DB_DEFAULT = '~/Library/Pioneer/rekordbox/master.db'
// ponytail: literal macOS default (>95% of installs); pyrekordbox
// auto-detection would need a sidecar route — add if Windows lands pre-M5.

export function usePathFields(onError: (message: string) => void) {
  const settings = useSettingsStore()
  const dbPath = ref('')
  const storageRoot = ref('')
  const state = reactive<Record<PathKey, PathState>>({
    rekordbox_db_path: 'unknown',
    storage_root: 'unknown',
  })
  const message = reactive<Record<PathKey, string | null>>({
    rekordbox_db_path: null,
    storage_root: null,
  })

  const valueOf = (field: PathKey) => (field === 'rekordbox_db_path' ? dbPath : storageRoot)

  async function save(field: PathKey): Promise<boolean> {
    const value = valueOf(field).value.trim()
    if (!value) {
      state[field] = 'unknown'
      message[field] = null
      return false
    }
    state[field] = 'checking'
    message[field] = null
    try {
      await settings.update({ [field]: value })
      state[field] = 'valid' // a ✓ means the SERVER found it (B3)
      return true
    } catch (cause) {
      state[field] = 'invalid'
      message[field] = cause instanceof ApiError ? cause.message : null
      if (!(cause instanceof ApiError)) onError(String(cause))
      return false
    }
  }

  /** Load stored values and RE-VALIDATE them (B3: never an optimistic ✓). */
  async function init() {
    if (!settings.loaded) await settings.load()
    dbPath.value = settings.values?.rekordbox_db_path ?? ''
    storageRoot.value = settings.values?.storage_root ?? ''
    if (dbPath.value) void save('rekordbox_db_path')
    if (storageRoot.value) void save('storage_root')
  }

  return { dbPath, storageRoot, state, message, save, init }
}

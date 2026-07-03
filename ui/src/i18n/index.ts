import { createI18n } from 'vue-i18n'

import { en } from './en'
import { fr } from './fr'

// Locale is bound to settings.language once the settings store exists (M4.4);
// localStorage only caches the last known value for pre-settings boot.
const cached = typeof localStorage === 'undefined' ? null : localStorage.getItem('syncbox.locale')

export const i18n = createI18n({
  legacy: false,
  locale: cached === 'en' || cached === 'fr' ? cached : 'fr',
  fallbackLocale: 'en',
  messages: { en, fr },
})

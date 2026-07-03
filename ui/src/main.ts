import '@fontsource/geist-sans/400.css'
import '@fontsource/geist-sans/500.css'
import '@fontsource/geist-sans/600.css'
import '@fontsource/geist-sans/700.css'
import '@fontsource/geist-mono/400.css'
import '@fontsource/geist-mono/500.css'
import '@fontsource/geist-mono/600.css'
import './styles/tokens.css'
import './styles/base.css'

import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { i18n } from './i18n'
import { restoreLastRoute, router } from './router'
import { useJobsStore } from './stores/jobs'
import { useStatusStore } from './stores/status'

const app = createApp(App).use(createPinia()).use(router).use(i18n)

restoreLastRoute(router)
useStatusStore().start()
useJobsStore().start()

app.mount('#app')

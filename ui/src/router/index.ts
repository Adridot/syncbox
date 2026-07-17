/* Real router (SPEC-DESIGN §3.1/§5): 6 destinations, deep-linkable health
   tabs (#/health/smartfixes) and missing-center scope, unknown route ->
   Dashboard (explicit default, NEVER Settings), native back/forward. The
   app always opens on the Dashboard — no last-route restore (owner feedback
   07/07: launch = overview, not wherever you were). */

import {
  createRouter,
  createWebHashHistory,
  type Router,
  type RouterHistory,
} from 'vue-router'

import DashboardScreen from '../screens/DashboardScreen.vue'
import EventsScreen from '../screens/EventsScreen.vue'
import HealthHubScreen from '../screens/HealthHubScreen.vue'
import HistoryScreen from '../screens/HistoryScreen.vue'
import LibraryScreen from '../screens/LibraryScreen.vue'
import MissingCenterScreen from '../screens/MissingCenterScreen.vue'
import SettingsScreen from '../screens/SettingsScreen.vue'

export const HEALTH_TABS = [
  'duplicates',
  'missing',
  'untagged',
  'smartfixes',
  'backups',
] as const
export type HealthTab = (typeof HEALTH_TABS)[number]

export const MISSING_SCOPES = ['library', 'event', 'collection'] as const
export type MissingScope = (typeof MISSING_SCOPES)[number]

export function createAppRouter(history: RouterHistory = createWebHashHistory()): Router {
  const router = createRouter({
    history,
    routes: [
      { path: '/', name: 'dashboard', component: DashboardScreen },
      { path: '/library', name: 'library', component: LibraryScreen },
      { path: '/events', name: 'events', component: EventsScreen },
      { path: '/history', name: 'history', component: HistoryScreen },
      { path: '/health/:tab?', name: 'health', component: HealthHubScreen, props: true },
      {
        path: '/missing/:scope?',
        name: 'missing',
        component: MissingCenterScreen,
        props: true,
      },
      { path: '/settings', name: 'settings', component: SettingsScreen },
      // Unknown route -> Dashboard, explicit default (never Settings).
      { path: '/:pathMatch(.*)*', redirect: '/' },
    ],
  })
  // Param validation lives in a GLOBAL guard: per-route beforeEnter does not
  // re-fire when only the params change (same route record).
  router.beforeEach((to) => {
    if (to.name === 'health') {
      const tab = to.params.tab
      if (!tab || !HEALTH_TABS.includes(tab as HealthTab))
        return { path: `/health/${HEALTH_TABS[0]}`, replace: true }
    }
    if (to.name === 'missing') {
      const scope = to.params.scope
      if (scope && !MISSING_SCOPES.includes(scope as MissingScope))
        return { path: '/missing', replace: true }
    }
    return true
  })
  return router
}

export const router = createAppRouter()

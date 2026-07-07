import { beforeEach, expect, test } from 'vitest'
import { createMemoryHistory } from 'vue-router'

import { createAppRouter } from '../index'

beforeEach(() => localStorage.clear())

async function makeRouter() {
  const router = createAppRouter(createMemoryHistory())
  await router.push('/')
  return router
}

test('unknown route falls back to Dashboard, never Settings', async () => {
  const router = await makeRouter()
  await router.push('/definitely-not-a-screen')
  expect(router.currentRoute.value.name).toBe('dashboard')
})

test('health deep link resolves its tab; bad tab -> explicit default tab', async () => {
  const router = await makeRouter()
  await router.push('/health/smartfixes')
  expect(router.currentRoute.value.params.tab).toBe('smartfixes')

  await router.push('/health')
  expect(router.currentRoute.value.fullPath).toBe('/health/duplicates')

  await router.push('/health/nope')
  expect(router.currentRoute.value.fullPath).toBe('/health/duplicates')
})

test('missing center scope param validates', async () => {
  const router = await makeRouter()
  await router.push('/missing/collection')
  expect(router.currentRoute.value.params.scope).toBe('collection')
  await router.push('/missing/nope')
  expect(router.currentRoute.value.fullPath).toBe('/missing')
})

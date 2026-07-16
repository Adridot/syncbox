import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { KeepAlive, defineComponent, h, nextTick, ref } from 'vue'

import { useRefreshOnReturn } from '../refresh'

function makeChild(calls: { count: number }) {
  return defineComponent({
    name: 'Child',
    setup() {
      useRefreshOnReturn(() => {
        calls.count += 1
      })
      return () => h('div')
    },
  })
}

test('inside keep-alive: one load on mount, one silent refresh per re-entry', async () => {
  const calls = { count: 0 }
  const Child = makeChild(calls)
  const show = ref(true)
  const Parent = defineComponent({
    setup() {
      return () => h(KeepAlive, null, [show.value ? h(Child) : null])
    },
  })

  mount(Parent)
  await nextTick()
  expect(calls.count).toBe(1) // mounted + first activation dedupe to ONE load

  show.value = false
  await nextTick()
  show.value = true
  await nextTick()
  expect(calls.count).toBe(2) // re-entry refreshes (silently — no state reset)
})

test('outside keep-alive: degrades to a plain onMounted load', async () => {
  const calls = { count: 0 }
  mount(makeChild(calls))
  await nextTick()
  expect(calls.count).toBe(1)
})

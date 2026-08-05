import { mount } from '@vue/test-utils'
import { beforeEach, expect, test, vi } from 'vitest'
import { nextTick } from 'vue'

import { i18n } from '../../i18n'
import { openSpotify } from '../../shell'
import SpotifyAttributionLink from '../SpotifyAttributionLink.vue'

vi.mock('../../shell', () => ({ openSpotify: vi.fn() }))

beforeEach(() => vi.mocked(openSpotify).mockReset().mockResolvedValue(undefined))

function mountLink(kind: 'playlist' | 'track', spotifyId: string) {
  return mount(SpotifyAttributionLink, {
    props: { kind, spotifyId },
    global: { plugins: [i18n] },
  })
}

// The reveal contract needs a real `.hover-reveal` ancestor in the DOM.
function mountInHoverReveal() {
  const host = document.createElement('div')
  host.className = 'hover-reveal'
  document.body.appendChild(host)
  const wrapper = mount(SpotifyAttributionLink, {
    props: { kind: 'track' as const, spotifyId: '37i9dQZF1DXcBWIGoYBM5M' },
    global: { plugins: [i18n] },
    attachTo: host,
  })
  return {
    wrapper,
    host,
    cleanup() {
      wrapper.unmount()
      host.remove()
    },
  }
}

test('prefers the desktop app URI and falls back to the canonical web URL', async () => {
  const id = '37i9dQZF1DXcBWIGoYBM5M'
  const wrapper = mountLink('track', id)

  expect(wrapper.get('button').attributes('title')).toBe('Ouvrir dans Spotify')
  await wrapper.get('button').trigger('click')

  expect(openSpotify).toHaveBeenCalledWith(
    `spotify:track:${id}`,
    `https://open.spotify.com/track/${id}`,
  )
})

test('shows a local failure state when the opener rejects', async () => {
  vi.mocked(openSpotify).mockRejectedValueOnce(new Error('opener failed'))
  const wrapper = mountLink('playlist', '37i9dQZF1DXcBWIGoYBM5M')

  await wrapper.get('button').trigger('click')

  expect(wrapper.get('button').attributes('data-failed')).toBe('true')
  expect(wrapper.get('button').attributes('title')).toContain("n'a pas pu être ouvert")
})

test('pointer movement over the row reveals the arrow, moving away hides it', async () => {
  const { wrapper, cleanup } = mountInHoverReveal()

  // hidden = structurally absent (no icon in the DOM, nothing to ghost)
  expect(wrapper.find('svg').exists()).toBe(false)
  // hit-test based: the event's target inside the container is what counts,
  // never WebKit's (stale) enter/leave bookkeeping
  wrapper.get('button').element.dispatchEvent(new Event('pointermove', { bubbles: true }))
  await nextTick()
  expect(wrapper.get('button').attributes('data-shown')).toBe('true')
  expect(wrapper.find('svg').exists()).toBe(true)

  document.body.dispatchEvent(new Event('pointermove', { bubbles: true }))
  await nextTick()
  expect(wrapper.find('svg').exists()).toBe(false)
  cleanup()
})

test('any scroll or wheel hides a revealed arrow until the pointer moves again', async () => {
  const { wrapper, host, cleanup } = mountInHoverReveal()

  host.dispatchEvent(new Event('pointermove', { bubbles: true }))
  await nextTick()
  expect(wrapper.find('svg').exists()).toBe(true)

  // scroll events do not bubble: the window listener must catch a nested
  // scroll container's event in the CAPTURE phase (virtualized lists)
  host.dispatchEvent(new Event('scroll'))
  await nextTick()
  expect(wrapper.find('svg').exists()).toBe(false)

  // re-hover after a scroll reveals again
  host.dispatchEvent(new Event('pointermove', { bubbles: true }))
  await nextTick()
  expect(wrapper.find('svg').exists()).toBe(true)

  // wheel is the trackpad input itself — it must hide even if no scroll
  // event reaches the window (WKWebView belt-and-suspenders)
  host.dispatchEvent(new Event('wheel', { bubbles: true }))
  await nextTick()
  expect(wrapper.find('svg').exists()).toBe(false)
  cleanup()
})

test('at most one arrow is revealed across containers', async () => {
  const first = mountInHoverReveal()
  const second = mountInHoverReveal()

  first.host.dispatchEvent(new Event('pointermove', { bubbles: true }))
  await nextTick()
  expect(first.wrapper.find('svg').exists()).toBe(true)
  expect(second.wrapper.find('svg').exists()).toBe(false)

  second.host.dispatchEvent(new Event('pointermove', { bubbles: true }))
  await nextTick()
  expect(first.wrapper.find('svg').exists()).toBe(false)
  expect(second.wrapper.find('svg').exists()).toBe(true)
  first.cleanup()
  second.cleanup()
})

test('keyboard focus inside the row reveals the arrow and keeps it while focus stays', async () => {
  const { wrapper, host, cleanup } = mountInHoverReveal()
  const outside = document.createElement('button')
  document.body.appendChild(outside)

  host.dispatchEvent(new Event('focusin', { bubbles: true }))
  await nextTick()
  expect(wrapper.find('svg').exists()).toBe(true)

  host.dispatchEvent(
    new FocusEvent('focusout', { bubbles: true, relatedTarget: outside }),
  )
  await nextTick()
  expect(wrapper.find('svg').exists()).toBe(false)
  outside.remove()
  cleanup()
})

test('permanent sites (no hover-reveal ancestor) always show the arrow', async () => {
  const wrapper = mount(SpotifyAttributionLink, {
    props: { kind: 'track' as const, spotifyId: '37i9dQZF1DXcBWIGoYBM5M' },
    global: { plugins: [i18n] },
    attachTo: document.body,
  })

  await nextTick() // permanentSite flips in onMounted, re-render is queued
  expect(wrapper.find('svg').exists()).toBe(true)
  document.body.dispatchEvent(new Event('pointermove', { bubbles: true }))
  window.dispatchEvent(new Event('scroll'))
  await nextTick()
  expect(wrapper.find('svg').exists()).toBe(true)
  wrapper.unmount()
})

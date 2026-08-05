// Shared hover-reveal tracking (spotify-attribution-reveal spec).
//
// WKWebView keeps a stale hover/boundary-event chain when rows move under a
// still pointer during scroll: CSS :hover ghosts, and pointerenter/leave
// are unreliable for the same reason. So ONE module-level state tracks the
// hovered `.hover-reveal` container from pointermove hit-tests (always
// fresh), and any scroll/wheel clears it — wheel is the trackpad input
// itself, it cannot be missed. At most one container is ever active.
import { ref } from 'vue'

export const activeHoverReveal = ref<Element | null>(null)

let uses = 0

const trackPointer = (event: Event) => {
  const target = event.target instanceof Element ? event.target : null
  activeHoverReveal.value = target?.closest('.hover-reveal') ?? null
}
const clearActive = () => {
  if (activeHoverReveal.value) activeHoverReveal.value = null
}
const clearWhenLeavingWindow = (event: Event) => {
  if (!(event as PointerEvent).relatedTarget) clearActive()
}

export function acquireHoverReveal(): void {
  if (uses++ > 0) return
  window.addEventListener('pointermove', trackPointer, { capture: true, passive: true })
  window.addEventListener('scroll', clearActive, { capture: true, passive: true })
  window.addEventListener('wheel', clearActive, { capture: true, passive: true })
  window.addEventListener('pointerout', clearWhenLeavingWindow, { capture: true, passive: true })
}

export function releaseHoverReveal(container: Element): void {
  if (activeHoverReveal.value === container) activeHoverReveal.value = null
  if (--uses > 0) return
  window.removeEventListener('pointermove', trackPointer, { capture: true })
  window.removeEventListener('scroll', clearActive, { capture: true })
  window.removeEventListener('wheel', clearActive, { capture: true })
  window.removeEventListener('pointerout', clearWhenLeavingWindow, { capture: true })
}

/* Windowed rows for the big track tables (Library review table, Events
   tracklist): only ~viewport rows exist in the DOM, absolutely positioned
   inside a wrapper sized to the virtualizer's total. Row markup and CSS stay
   untouched — windowing only changes row positioning (ui-performance spec). */

import {
  type Rect,
  type Virtualizer,
  observeElementRect,
  useVirtualizer,
} from '@tanstack/vue-virtual'
import { type ComponentPublicInstance, type Ref, computed, onActivated, onDeactivated } from 'vue'

export function useVirtualRows<T extends { id: number }>(
  rows: () => T[],
  bodyEl: Ref<HTMLElement | null>,
  estimateSize = 56,
) {
  // Own scroll container (Library's .table-body) or nearest scrollable
  // ancestor (the Events tracklist scrolls in App's .main). Bare mounts
  // (unit tests, one-off screens) have neither: fall back to the wrapper
  // itself — initialRect still windows the list there.
  function scrollElement(): HTMLElement | null {
    const el = bodyEl.value
    if (!el) return null
    return (el.closest('.table-body, .main') as HTMLElement | null) ?? el
  }

  // Offset of the list start inside the scroll container (0 when the
  // container IS the list body). Re-read whenever the options computed
  // re-evaluates (rows swap, mount). ponytail: not reactive to layout
  // shifts above the list (banners toggling) — the overscan absorbs them.
  function scrollMargin(): number {
    const el = bodyEl.value
    const scroller = scrollElement()
    if (!el || !scroller || el === scroller) return 0
    return el.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop
  }

  // Keep-alive detach resets an own scroll container to 0, and a shared one
  // (App's .main) gets clamped by shorter screens in between — both before
  // onDeactivated could read them. The virtualizer's scrollOffset still
  // holds the last offset its scroll listener saw: restore from it so
  // returning to the screen lands where the user left it (ui-performance:
  // restore contract). No-ops outside keep-alive.
  let savedScrollTop = 0
  onDeactivated(() => {
    savedScrollTop = virtualizer.value.scrollOffset ?? 0
  })
  onActivated(() => {
    const el = scrollElement()
    if (el && savedScrollTop) el.scrollTop = savedScrollTop
  })

  const virtualizer = useVirtualizer(
    computed(() => ({
      count: rows().length,
      getScrollElement: scrollElement,
      estimateSize: () => estimateSize,
      overscan: 10,
      // stable ids: the measurement cache and row vnodes survive silent
      // refreshes, so identical data produces zero DOM mutation
      getItemKey: (index: number) => rows()[index]?.id ?? index,
      scrollMargin: scrollMargin(),
      // jsdom (tests) has no ResizeObserver and zero-size rects: a synthetic
      // viewport keeps windowing deterministic there; real measured rects
      // take over in the app (zero rects are dropped so they never clobber
      // the synthetic one).
      initialRect: { width: 800, height: 600 },
      observeElementRect: (instance: Virtualizer<HTMLElement, Element>, cb: (rect: Rect) => void) =>
        observeElementRect(instance, (rect) => {
          if (rect.height > 0) cb(rect)
        }),
    })),
  )

  /** Rendered slice: each virtual item paired with its data row. */
  const rowItems = computed(() =>
    virtualizer.value.getVirtualItems().map((item) => ({ item, row: rows()[item.index] as T })),
  )
  const totalSize = computed(() => virtualizer.value.getTotalSize())

  /** Function ref for each row: dynamic height measurement (2-line clamped
      titles, error lines growing). Zero height means jsdom — keep the
      estimate so windowing stays put in tests. */
  function measure(el: Element | ComponentPublicInstance | null) {
    if (el instanceof Element && el.getBoundingClientRect().height > 0)
      virtualizer.value.measureElement(el)
  }

  /** Positioning style for a row — item.start includes scrollMargin. */
  function rowStyle(item: { start: number }) {
    return { transform: `translateY(${item.start - virtualizer.value.options.scrollMargin}px)` }
  }

  return { rowItems, totalSize, measure, rowStyle }
}

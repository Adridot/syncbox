<script setup lang="ts">
// Shared dialog container (SPEC-DESIGN §6/§8): overlay backdrop + slide-up,
// closes on esc and backdrop click. A11y basics (M4.13): aria-modal, initial
// focus into the dialog, a Tab focus trap, and focus restored to the trigger
// on close.
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

defineProps<{ width?: string }>()
const emit = defineEmits<{ close: [] }>()

const modal = ref<HTMLElement | null>(null)
let lastFocused: HTMLElement | null = null

function focusables(): HTMLElement[] {
  if (!modal.value) return []
  return [
    ...modal.value.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ]
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    emit('close')
    return
  }
  if (event.key !== 'Tab') return
  const items = focusables()
  if (!items.length) return
  const first = items[0]
  const last = items[items.length - 1]
  const active = document.activeElement as HTMLElement
  // Trap Tab within the dialog (both directions).
  if (event.shiftKey && active === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}

onMounted(async () => {
  lastFocused = document.activeElement as HTMLElement
  document.addEventListener('keydown', onKeydown)
  await nextTick()
  focusables()[0]?.focus()
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  lastFocused?.focus?.()
})
</script>

<template>
  <Teleport to="body">
    <div class="backdrop" @click.self="emit('close')">
      <div
        ref="modal"
        class="modal"
        role="dialog"
        aria-modal="true"
        :style="{ maxWidth: width ?? '560px' }"
      >
        <slot />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(5, 7, 10, 0.7);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
  padding: 24px;
}
.modal {
  background: var(--surface-2);
  border: 1px solid var(--border-2);
  border-radius: var(--radius-modal);
  box-shadow: var(--shadow-overlay);
  width: 100%;
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  animation: slideup var(--motion-modal) ease-out;
}
</style>

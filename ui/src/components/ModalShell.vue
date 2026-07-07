<script setup lang="ts">
// Shared dialog container (SPEC-DESIGN §6): overlay backdrop + slide-up,
// closes on esc and backdrop click, minimal focus trap (M4.13 a11y): focus
// moves into the dialog on open, Tab cycles inside it, and returns to the
// opener on close.
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps<{ width?: string }>()
const emit = defineEmits<{ close: [] }>()

const modal = ref<HTMLElement | null>(null)
let opener: HTMLElement | null = null

function focusables(): HTMLElement[] {
  return [
    ...(modal.value?.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    ) ?? []),
  ].filter((el) => !el.hasAttribute('disabled'))
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
  const active = document.activeElement as HTMLElement | null
  if (event.shiftKey && (active === first || !modal.value?.contains(active))) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (active === last || !modal.value?.contains(active))) {
    event.preventDefault()
    first.focus()
  }
}

onMounted(() => {
  opener = document.activeElement as HTMLElement | null
  document.addEventListener('keydown', onKeydown)
  ;(focusables()[0] ?? modal.value)?.focus()
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  opener?.focus()
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
        tabindex="-1"
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

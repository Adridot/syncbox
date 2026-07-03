<script setup lang="ts">
// Shared dialog container (SPEC-DESIGN §6): overlay backdrop + slide-up,
// closes on esc and backdrop click. Focus trap basics land in M4.13 a11y.
import { onBeforeUnmount, onMounted } from 'vue'

defineProps<{ width?: string }>()
const emit = defineEmits<{ close: [] }>()

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div class="backdrop" @click.self="emit('close')">
      <div class="modal" role="dialog" aria-modal="true" :style="{ maxWidth: width ?? '560px' }">
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

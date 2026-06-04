<script setup lang="ts">
import { AlertTriangle, CheckCircle2, Info, X } from "@lucide/vue";
import { useUiStore } from "../stores/ui";
import type { ToastKind } from "../stores/ui";

const ui = useUiStore();

const styles: Record<ToastKind, string> = {
  success: "border-secondary/30 bg-secondary/10 text-secondary",
  error: "border-error/30 bg-error-container text-on-error-container",
  info: "border-primary/30 bg-primary/10 text-primary",
};

const icons: Record<ToastKind, unknown> = {
  success: CheckCircle2,
  error: AlertTriangle,
  info: Info,
};
</script>

<template>
  <div class="pointer-events-none absolute bottom-4 right-4 z-50 flex w-full max-w-md flex-col gap-2">
    <TransitionGroup name="toast">
      <div
        v-for="toast in ui.toasts"
        :key="toast.id"
        class="pointer-events-auto flex min-h-11 items-start gap-3 rounded border px-4 py-2.5 text-sm shadow-xl backdrop-blur"
        :class="styles[toast.kind]"
        role="status"
      >
        <component :is="icons[toast.kind]" :size="18" aria-hidden="true" class="mt-0.5 shrink-0" />
        <span class="line-clamp-5 min-w-0 flex-1 break-words" :title="toast.message">{{ toast.message }}</span>
        <button
          type="button"
          class="mt-0.5 shrink-0 opacity-60 transition-opacity hover:opacity-100"
          aria-label="Dismiss"
          @click="ui.dismissToast(toast.id)"
        >
          <X :size="16" aria-hidden="true" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.22s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateY(8px) scale(0.98);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(16px);
}
.toast-move {
  transition: transform 0.22s ease;
}
</style>

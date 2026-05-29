<script setup lang="ts">
withDefaults(
  defineProps<{
    tone?: "ok" | "warn" | "active" | "error" | "muted" | "neutral";
  }>(),
  {
    tone: "neutral"
  }
);
</script>

<template>
  <span
    class="inline-flex min-h-6 items-center rounded px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider"
    :class="{
      'border border-secondary/20 bg-secondary/10 text-secondary': tone === 'ok',
      'border border-tertiary/30 bg-tertiary/10 text-tertiary': tone === 'warn',
      'border border-primary/30 bg-primary/10 text-primary': tone === 'active',
      'border border-error/30 bg-error/10 text-error': tone === 'error',
      'border border-outline-variant bg-surface-variant text-on-surface-variant': tone === 'muted',
      'border border-outline bg-surface-container-high text-on-surface': tone === 'neutral'
    }"
  >
    <slot />
  </span>
</template>


<script setup lang="ts">
defineProps<{
  title: string;
  value: string | number;
  detail?: string;
  tone?: "primary" | "secondary" | "tertiary" | "muted" | "error";
  icon: unknown;
}>();
</script>

<template>
  <div
    class="rounded-xl border border-outline-variant bg-surface-container-high p-5 transition-colors hover:border-primary"
  >
    <div class="mb-3 flex items-center gap-3">
      <div
        class="grid h-10 w-10 place-items-center rounded-full"
        :class="{
          'bg-primary/10 text-primary': tone === 'primary' || !tone,
          'bg-secondary/10 text-secondary': tone === 'secondary',
          'bg-tertiary/10 text-tertiary': tone === 'tertiary',
          'bg-error/10 text-error': tone === 'error',
          'bg-surface-variant text-on-surface-variant': tone === 'muted'
        }"
      >
        <component :is="icon" :size="20" aria-hidden="true" />
      </div>
      <h3 class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">
        {{ title }}
      </h3>
    </div>
    <div class="text-3xl font-bold text-on-surface">{{ value }}</div>
    <p v-if="detail" class="mt-2 text-xs text-on-surface-variant">{{ detail }}</p>
  </div>
</template>


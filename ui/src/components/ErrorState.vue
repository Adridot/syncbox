<script setup lang="ts">
// Actionable error state (SPEC-DESIGN §11.2 correctifs): message + actions
// slot (e.g. "Réessayer" / "Connecter mon compte Spotify").
defineProps<{ title: string; body?: string }>()
</script>

<template>
  <div class="error" role="alert">
    <div class="glyph">⚠</div>
    <h3>{{ title }}</h3>
    <p v-if="body">{{ body }}</p>
    <div class="actions"><slot /></div>
  </div>
</template>

<style scoped>
.error {
  text-align: center;
  padding: 42px 24px;
  color: var(--text-secondary);
}
.glyph {
  width: 52px;
  height: 52px;
  border-radius: var(--radius-card);
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  display: grid;
  place-content: center;
  font-size: 22px;
  margin: 0 auto 14px;
}
h3 {
  font: var(--text-h3);
  color: var(--text-primary);
  margin: 0;
}
p {
  font-size: 13px;
  margin: 6px auto 0;
  max-width: 380px;
  line-height: 1.5;
}
.actions {
  margin-top: 16px;
  display: flex;
  gap: 10px;
  justify-content: center;
}
</style>

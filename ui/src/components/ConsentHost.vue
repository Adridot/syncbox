<script setup lang="ts">
// 428 consent broker host (M4-PLAN §4): the API client asks HERE before
// re-calling once with the consent flag. Concurrent consents are QUEUED
// FIFO — never a single overwritten slot that would strand a promise and
// leave jobRunning stuck (REMARKS review finding). Consent is per-call,
// never remembered.
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { type ApiErrorBody, setConsentBroker } from '../api/client'
import AnlzReplaceModal from './AnlzReplaceModal.vue'
import IrreversibleDeleteModal from './IrreversibleDeleteModal.vue'

interface PendingConsent {
  body: ApiErrorBody
  resolve: (granted: boolean) => void
}

const queue = ref<PendingConsent[]>([])

onMounted(() =>
  setConsentBroker(
    (body) =>
      new Promise<boolean>((resolve) => {
        queue.value.push({ body, resolve })
      }),
  ),
)
onBeforeUnmount(() => setConsentBroker(null))

function settle(granted: boolean) {
  queue.value.shift()?.resolve(granted)
}
</script>

<template>
  <IrreversibleDeleteModal
    v-if="queue[0]?.body.consent === 'permanent_delete'"
    :path="queue[0].body.path"
    @cancel="settle(false)"
    @confirm="settle(true)"
  />
  <AnlzReplaceModal
    v-else-if="queue[0]?.body.consent === 'anlz'"
    @cancel="settle(false)"
    @confirm="settle(true)"
  />
</template>

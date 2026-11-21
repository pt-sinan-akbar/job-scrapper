<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useDiscordSettingsStore } from '@/modules/discord/presentation/stores/useDiscordSettingsStore'
import { isSendableToDiscord } from '@/modules/scrapes/domain/entities/Scrape'
import { toDiscordStatusView } from '@/modules/scrapes/presentation/components/scrapeStatus'
import { useScrapeStore } from '@/modules/scrapes/presentation/stores/useScrapeStore'
import { Button } from '@/shared/components/ui/button'
import { cn } from '@/shared/utils/cn'

const SENDING_MESSAGE = 'Sending the last result to Discord'

const settingsStore = useDiscordSettingsStore()
const scrapeStore = useScrapeStore()

const isDiscordReady = computed(() => {
  const settings = settingsStore.settings
  return settings !== null && settings.isConfigured && settings.defaultChannelId !== null
})
const canSend = computed(() => {
  if (!isDiscordReady.value || scrapeStore.isScraping || scrapeStore.isSendingLatest) {
    return false
  }
  return isSendableToDiscord(scrapeStore.latestScrape?.record ?? null)
})
const outcomeView = computed(() => {
  if (scrapeStore.isSendingLatest || scrapeStore.latestSendOutcome === null) {
    return null
  }
  return toDiscordStatusView(scrapeStore.latestSendOutcome)
})
const statusMessage = computed(() => {
  if (scrapeStore.isSendingLatest) {
    return SENDING_MESSAGE
  }
  if (outcomeView.value === null || outcomeView.value.toastKind === 'error') {
    return null
  }
  return outcomeView.value.label
})
const errorMessage = computed(() => {
  if (scrapeStore.latestSendError !== null) {
    return scrapeStore.latestSendError
  }
  if (outcomeView.value?.toastKind === 'error') {
    return outcomeView.value.label
  }
  return null
})
const isSent = computed(() => outcomeView.value?.toastKind === 'success')

onMounted(() => {
  void scrapeStore.loadLatest()
})

onUnmounted(() => {
  scrapeStore.stopLatestSend()
})
</script>

<template>
  <p
    v-if="statusMessage"
    data-slot="send-last-result-status"
    role="status"
    :class="cn('mr-auto min-w-0 text-body-sm', isSent ? 'font-semibold text-accent' : 'text-ink')"
  >
    {{ statusMessage }}
  </p>
  <p
    v-if="errorMessage"
    data-slot="send-last-result-error"
    role="alert"
    class="mr-auto min-w-0 text-body-sm text-danger"
  >
    {{ errorMessage }}
  </p>
  <Button type="button" :disabled="!canSend" @click="scrapeStore.sendLatestToDiscord">
    {{ scrapeStore.isSendingLatest ? 'Sending' : 'Send last result' }}
  </Button>
</template>

import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import {
  countChars,
  MAX_MESSAGE_CHARS,
  toMentionPrefix,
  type DiscordChannel,
  type DiscordContent,
  type DiscordSendResult,
  type DiscordSettings,
} from '@/modules/discord/domain/entities/Discord'
import { requireDiscordUseCases } from '@/modules/discord/presentation/stores/discordUseCases'
import { toErrorMessage } from '@/shared/utils/errorMessage'
import type { LoadStatus } from '@/shared/utils/loadStatus'

const FALLBACK_ERROR_MESSAGE = 'Something went wrong. Try again.'

function hasChannel(channels: readonly DiscordChannel[], id: string | null): id is string {
  return id !== null && channels.some((channel) => channel.id === id)
}

function pickChannelId(
  channels: readonly DiscordChannel[],
  current: string | null,
  previousDefault: string | null,
  nextDefault: string | null,
): string | null {
  const isUserPick = current !== null && current !== previousDefault
  if (isUserPick && hasChannel(channels, current)) {
    return current
  }
  return hasChannel(channels, nextDefault) ? nextDefault : null
}

export const useDiscordComposeStore = defineStore('discordCompose', () => {
  const status = ref<LoadStatus>('idle')
  const channels = ref<DiscordChannel[]>([])
  const mentionUserId = ref<string | null>(null)
  const channelId = ref<string | null>(null)
  const mention = ref(true)
  const text = ref('')
  const previewMessages = ref<string[]>([])
  const sendResult = ref<DiscordSendResult | null>(null)
  const errorMessage = ref<string | null>(null)
  const previewError = ref<string | null>(null)
  const sendError = ref<string | null>(null)
  const isPreviewing = ref(false)
  const isSending = ref(false)
  let previewRequestId = 0
  let loadedSettings: DiscordSettings | null = null
  let previousDefaultId: string | null = null

  const hasMentionUser = computed(() => mentionUserId.value !== null)
  const isMentioned = computed(() => hasMentionUser.value && mention.value)
  const mentionPrefix = computed(() => toMentionPrefix(mentionUserId.value, isMentioned.value))
  const charCount = computed(() => countChars(mentionPrefix.value) + countChars(text.value))
  const isOverLimit = computed(() => charCount.value > MAX_MESSAGE_CHARS)
  const content = computed<DiscordContent | null>(() =>
    isOverLimit.value || text.value.trim() === '' ? null : { text: text.value },
  )
  const canPreview = computed(() => content.value !== null && !isPreviewing.value)
  const canSend = computed(
    () =>
      content.value !== null && channelId.value !== null && !isPreviewing.value && !isSending.value,
  )

  watch(
    [content, isMentioned],
    () => {
      previewRequestId += 1
      isPreviewing.value = false
      previewMessages.value = []
      previewError.value = null
    },
    { flush: 'sync' },
  )

  function isLoadedFor(settings: DiscordSettings): boolean {
    return loadedSettings === settings && status.value !== 'error'
  }

  function applyChannels(nextChannels: DiscordChannel[], settings: DiscordSettings): void {
    channelId.value = pickChannelId(
      nextChannels,
      channelId.value,
      previousDefaultId,
      settings.defaultChannelId,
    )
    channels.value = nextChannels
    mentionUserId.value = settings.mentionUserId
    previousDefaultId = settings.defaultChannelId
    status.value = 'ready'
  }

  async function load(settings: DiscordSettings): Promise<void> {
    if (isLoadedFor(settings)) {
      return
    }
    loadedSettings = settings
    status.value = 'loading'
    errorMessage.value = null
    try {
      const nextChannels = await requireDiscordUseCases().listChannels.execute()
      if (loadedSettings === settings) {
        applyChannels(nextChannels, settings)
      }
    } catch (error) {
      if (loadedSettings === settings) {
        errorMessage.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
        status.value = 'error'
      }
    }
  }

  async function preview(): Promise<void> {
    const current = content.value
    if (current === null) {
      return
    }
    previewRequestId += 1
    const requestId = previewRequestId
    isPreviewing.value = true
    previewError.value = null
    try {
      const messages = await requireDiscordUseCases().previewMessage.execute(
        isMentioned.value,
        current,
      )
      if (requestId === previewRequestId) {
        previewMessages.value = messages
      }
    } catch (error) {
      if (requestId === previewRequestId) {
        previewMessages.value = []
        previewError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      }
    } finally {
      if (requestId === previewRequestId) {
        isPreviewing.value = false
      }
    }
  }

  async function send(): Promise<DiscordSendResult | null> {
    const current = content.value
    const channel = channelId.value
    if (current === null || channel === null || isSending.value) {
      return null
    }
    isSending.value = true
    sendError.value = null
    sendResult.value = null
    try {
      sendResult.value = await requireDiscordUseCases().sendMessage.execute(
        channel,
        isMentioned.value,
        current,
      )
      return sendResult.value
    } catch (error) {
      sendError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      return null
    } finally {
      isSending.value = false
    }
  }

  return {
    status,
    channels,
    channelId,
    mention,
    text,
    previewMessages,
    sendResult,
    errorMessage,
    previewError,
    sendError,
    isPreviewing,
    isSending,
    hasMentionUser,
    charCount,
    isOverLimit,
    canPreview,
    canSend,
    load,
    preview,
    send,
  }
})

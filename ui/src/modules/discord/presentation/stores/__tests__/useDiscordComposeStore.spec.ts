import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { DiscordChannel, DiscordSettings } from '@/modules/discord/domain/entities/Discord'
import { provideDiscordUseCases } from '@/modules/discord/presentation/stores/discordUseCases'
import { useDiscordComposeStore } from '@/modules/discord/presentation/stores/useDiscordComposeStore'

const getSettings = { execute: vi.fn() }
const saveSettings = { execute: vi.fn() }
const testConnection = { execute: vi.fn() }
const listChannels = { execute: vi.fn() }
const previewMessage = { execute: vi.fn() }
const sendMessage = { execute: vi.fn() }

const CHANNEL_ID = '12345678901234567'
const USER_ID = '76543210987654321'

const CHANNELS: DiscordChannel[] = [
  { id: CHANNEL_ID, name: 'jobs', guildId: '1', guildName: 'Home' },
  { id: '22345678901234567', name: 'general', guildId: '1', guildName: 'Home' },
]

const SETTINGS: DiscordSettings = {
  isConfigured: true,
  tokenHint: '••••1234',
  defaultChannelId: CHANNEL_ID,
  mentionUserId: USER_ID,
  messageTemplate: '{title}',
  maxChars: 1900,
  updatedAt: null,
}

function deferred<T>(): {
  promise: Promise<T>
  resolve: (value: T) => void
  reject: (reason: unknown) => void
} {
  let resolve: (value: T) => void = () => undefined
  let reject: (reason: unknown) => void = () => undefined
  const promise = new Promise<T>((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}

async function loadedStore(settings: DiscordSettings = SETTINGS) {
  const store = useDiscordComposeStore()
  await store.load(settings)
  return store
}

describe('useDiscordComposeStore', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    provideDiscordUseCases({
      getSettings,
      saveSettings,
      testConnection,
      listChannels,
      previewMessage,
      sendMessage,
    })
    listChannels.execute.mockResolvedValue(CHANNELS)
  })

  describe('load', () => {
    it('loads the channels', async () => {
      const store = await loadedStore()

      expect(store.status).toBe('ready')
      expect(store.channels).toEqual(CHANNELS)
    })

    it('picks the default channel', async () => {
      const store = await loadedStore()

      expect(store.channelId).toBe(CHANNEL_ID)
    })

    it('leaves the channel empty when the default is not in the list', async () => {
      const store = await loadedStore({ ...SETTINGS, defaultChannelId: '99999999999999999' })

      expect(store.channelId).toBeNull()
    })

    it('leaves the channel empty when there is no default', async () => {
      const store = await loadedStore({ ...SETTINGS, defaultChannelId: null })

      expect(store.channelId).toBeNull()
    })

    it('turns mention on when a user id is saved', async () => {
      const store = await loadedStore()

      expect(store.hasMentionUser).toBe(true)
      expect(store.mention).toBe(true)
    })

    it('has no mention user without a saved user id', async () => {
      const store = await loadedStore({ ...SETTINGS, mentionUserId: null })

      expect(store.hasMentionUser).toBe(false)
    })

    it('shows an error when the channels fail', async () => {
      listChannels.execute.mockRejectedValue(new Error('Discord rejected the bot token.'))
      const store = await loadedStore()

      expect(store.status).toBe('error')
      expect(store.errorMessage).toBe('Discord rejected the bot token.')
    })

    it('does not load the channels again for the same settings', async () => {
      const store = await loadedStore()

      await store.load(SETTINGS)

      expect(listChannels.execute).toHaveBeenCalledTimes(1)
      expect(store.status).toBe('ready')
    })

    it('loads again for the same settings after a failed load', async () => {
      listChannels.execute.mockRejectedValueOnce(new Error('down'))
      const store = await loadedStore()

      await store.load(SETTINGS)

      expect(listChannels.execute).toHaveBeenCalledTimes(2)
      expect(store.status).toBe('ready')
    })

    it('keeps the picked channel when the settings are saved again', async () => {
      const store = await loadedStore()
      store.channelId = CHANNELS[1]!.id

      await store.load({ ...SETTINGS })

      expect(listChannels.execute).toHaveBeenCalledTimes(2)
      expect(store.channelId).toBe(CHANNELS[1]!.id)
    })

    it('follows a new default channel when the old default was still picked', async () => {
      const store = await loadedStore()

      await store.load({ ...SETTINGS, defaultChannelId: CHANNELS[1]!.id })

      expect(store.channelId).toBe(CHANNELS[1]!.id)
    })

    it('keeps mention off when the settings are saved again', async () => {
      const store = await loadedStore()
      store.mention = false

      await store.load({ ...SETTINGS })

      expect(store.mention).toBe(false)
    })

    it('ignores a channel list that arrives after newer settings', async () => {
      const first = deferred<DiscordChannel[]>()
      listChannels.execute.mockReturnValueOnce(first.promise).mockResolvedValueOnce([CHANNELS[1]!])
      const store = useDiscordComposeStore()

      const stale = store.load(SETTINGS)
      await store.load({ ...SETTINGS, defaultChannelId: CHANNELS[1]!.id })
      first.resolve(CHANNELS)
      await stale

      expect(store.channels).toEqual([CHANNELS[1]])
      expect(store.status).toBe('ready')
    })
  })

  describe('free text', () => {
    it('counts the mention prefix in the char count', async () => {
      const store = await loadedStore()
      store.text = 'hello'

      expect(store.charCount).toBe(`<@${USER_ID}>\n`.length + 5)
    })

    it('drops the prefix from the count when mention is off', async () => {
      const store = await loadedStore()
      store.text = 'hello'
      store.mention = false

      expect(store.charCount).toBe(5)
    })

    it('is over the limit past 2000 chars with the prefix', async () => {
      const store = await loadedStore()
      store.text = 'a'.repeat(2000)

      expect(store.isOverLimit).toBe(true)
      expect(store.canSend).toBe(false)
      expect(store.canPreview).toBe(false)
    })

    it('is at the limit when the text and prefix make exactly 2000', async () => {
      const store = await loadedStore()
      store.text = 'a'.repeat(2000 - `<@${USER_ID}>\n`.length)

      expect(store.isOverLimit).toBe(false)
      expect(store.canSend).toBe(true)
    })

    it('cannot send an empty text', async () => {
      const store = await loadedStore()
      store.text = '   '

      expect(store.canSend).toBe(false)
      expect(store.canPreview).toBe(false)
    })

    it('cannot send without a channel', async () => {
      const store = await loadedStore({ ...SETTINGS, defaultChannelId: null })
      store.text = 'hello'

      expect(store.canSend).toBe(false)
      expect(store.canPreview).toBe(true)
    })

    it('previews with the mention flag and the text', async () => {
      previewMessage.execute.mockResolvedValue(['<@1>\nhello'])
      const store = await loadedStore()
      store.text = 'hello'

      await store.preview()

      expect(previewMessage.execute).toHaveBeenCalledWith(true, { text: 'hello' })
      expect(store.previewMessages).toEqual(['<@1>\nhello'])
      expect(store.isPreviewing).toBe(false)
    })

    it('keeps the message when the preview fails', async () => {
      previewMessage.execute.mockRejectedValue(new Error('Text is too long'))
      const store = await loadedStore()
      store.text = 'hello'

      await store.preview()

      expect(store.previewError).toBe('Text is too long')
      expect(store.previewMessages).toEqual([])
    })

    it('clears the preview when the text changes', async () => {
      previewMessage.execute.mockResolvedValue(['hello'])
      const store = await loadedStore()
      store.text = 'hello'
      await store.preview()

      store.text = 'hello again'
      await Promise.resolve()

      expect(store.previewMessages).toEqual([])
    })

    it('clears the preview when mention changes', async () => {
      previewMessage.execute.mockResolvedValue(['hello'])
      const store = await loadedStore()
      store.text = 'hello'
      await store.preview()

      store.mention = false
      await Promise.resolve()

      expect(store.previewMessages).toEqual([])
    })

    it('sends to the channel with mention on', async () => {
      const result = { sent: 1, failed: 0, results: [] }
      sendMessage.execute.mockResolvedValue(result)
      const store = await loadedStore()
      store.text = 'hello'

      await expect(store.send()).resolves.toEqual(result)

      expect(sendMessage.execute).toHaveBeenCalledWith(CHANNEL_ID, true, {
        text: 'hello',
      })
      expect(store.sendResult).toEqual(result)
      expect(store.isSending).toBe(false)
    })

    it('sends mention off when no user id is saved', async () => {
      sendMessage.execute.mockResolvedValue({ sent: 1, failed: 0, results: [] })
      const store = await loadedStore({ ...SETTINGS, mentionUserId: null })
      store.text = 'hello'

      await store.send()

      expect(sendMessage.execute).toHaveBeenCalledWith(CHANNEL_ID, false, {
        text: 'hello',
      })
    })

    it('sends mention off when the box is unticked', async () => {
      sendMessage.execute.mockResolvedValue({ sent: 1, failed: 0, results: [] })
      const store = await loadedStore()
      store.text = 'hello'
      store.mention = false

      await store.send()

      expect(sendMessage.execute).toHaveBeenCalledWith(CHANNEL_ID, false, {
        text: 'hello',
      })
    })

    it('keeps the message and returns null when send fails', async () => {
      sendMessage.execute.mockRejectedValue(new Error("The bot can't post in that channel."))
      const store = await loadedStore()
      store.text = 'hello'

      await expect(store.send()).resolves.toBeNull()

      expect(store.sendError).toBe("The bot can't post in that channel.")
      expect(store.isSending).toBe(false)
    })

    it('does not send when it cannot send', async () => {
      const store = await loadedStore()

      await expect(store.send()).resolves.toBeNull()

      expect(sendMessage.execute).not.toHaveBeenCalled()
    })

    it('cannot send while a preview is in flight', async () => {
      const pending = deferred<string[]>()
      previewMessage.execute.mockReturnValue(pending.promise)
      const store = await loadedStore()
      store.text = 'hello'

      const previewing = store.preview()

      expect(store.isPreviewing).toBe(true)
      expect(store.canSend).toBe(false)

      pending.resolve(['hello'])
      await previewing

      expect(store.canSend).toBe(true)
    })

    it('cannot send again while a send is in progress', async () => {
      const pending = deferred<{ sent: number; failed: number; results: [] }>()
      sendMessage.execute.mockReturnValue(pending.promise)
      const store = await loadedStore()
      store.text = 'hello'

      const first = store.send()
      const second = store.send()

      expect(store.canSend).toBe(false)
      await expect(second).resolves.toBeNull()
      expect(sendMessage.execute).toHaveBeenCalledTimes(1)

      pending.resolve({ sent: 1, failed: 0, results: [] })
      await first
    })

    it('drops a preview that answers after the text changed', async () => {
      const pending = deferred<string[]>()
      previewMessage.execute.mockReturnValue(pending.promise)
      const store = await loadedStore()
      store.text = 'hello'

      const previewing = store.preview()
      store.text = 'hello again'
      await Promise.resolve()
      pending.resolve(['hello'])
      await previewing

      expect(store.previewMessages).toEqual([])
      expect(store.isPreviewing).toBe(false)
    })

    it('drops a failed preview that answers after the text changed', async () => {
      const pending = deferred<string[]>()
      previewMessage.execute.mockReturnValue(pending.promise)
      const store = await loadedStore()
      store.text = 'hello'

      const previewing = store.preview()
      store.text = 'hello again'
      await Promise.resolve()
      pending.reject(new Error('Text is too long'))
      await previewing

      expect(store.previewError).toBeNull()
    })

    it('keeps the newest preview when an older one answers last', async () => {
      const slow = deferred<string[]>()
      const fast = deferred<string[]>()
      previewMessage.execute.mockReturnValueOnce(slow.promise).mockReturnValueOnce(fast.promise)
      const store = await loadedStore()
      store.text = 'hello'

      const first = store.preview()
      store.text = 'hello again'
      await Promise.resolve()
      const second = store.preview()
      fast.resolve(['hello again'])
      await second
      slow.resolve(['hello'])
      await first

      expect(store.previewMessages).toEqual(['hello again'])
      expect(store.isPreviewing).toBe(false)
    })

    it('clears an earlier result when a new send starts', async () => {
      sendMessage.execute
        .mockResolvedValueOnce({ sent: 1, failed: 0, results: [] })
        .mockRejectedValueOnce(new Error('Nope'))
      const store = await loadedStore()
      store.text = 'hello'
      await store.send()

      await store.send()

      expect(store.sendResult).toBeNull()
      expect(store.sendError).toBe('Nope')
    })
  })
})

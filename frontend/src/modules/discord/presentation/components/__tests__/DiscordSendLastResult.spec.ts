import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import type { DiscordSettings } from '@/modules/discord/domain/entities/Discord'
import DiscordSendLastResult from '@/modules/discord/presentation/components/DiscordSendLastResult.vue'
import { useDiscordSettingsStore } from '@/modules/discord/presentation/stores/useDiscordSettingsStore'
import type { ScrapeDetail, ScrapeRecord } from '@/modules/scrapes/domain/entities/Scrape'
import { provideScrapeUseCases } from '@/modules/scrapes/presentation/stores/scrapeUseCases'
import {
  POLL_INTERVAL_MS,
  useScrapeStore,
} from '@/modules/scrapes/presentation/stores/useScrapeStore'

const getOptions = { execute: vi.fn() }
const getScrape = { execute: vi.fn() }
const getLatestScrape = { execute: vi.fn() }
const startScrape = { execute: vi.fn() }
const sendLatestScrapeToDiscord = { execute: vi.fn() }

const SETTINGS: DiscordSettings = {
  isConfigured: true,
  tokenHint: '••••1234',
  defaultChannelId: '12345678901234567',
  mentionUserId: null,
  messageTemplate: '{title}',
  maxChars: 1900,
  updatedAt: null,
}

const SCRAPE: ScrapeRecord = {
  id: 'run-1',
  status: 'succeeded',
  keywords: ['django'],
  sites: ['upwork'],
  startedAt: '2026-11-01T10:00:00+00:00',
  finishedAt: '2026-11-01T10:01:00+00:00',
  jobCount: 4,
  errorCount: 0,
  error: null,
  discordStatus: null,
  discordSent: 0,
  discordFailed: 0,
  discordError: null,
}

const SENDING: ScrapeRecord = { ...SCRAPE, discordStatus: 'sending' }

function asDetail(record: ScrapeRecord): ScrapeDetail {
  return { record, jobs: [], failures: [] }
}

function deferred<T>(): { promise: Promise<T>; resolve: (settled: T) => void } {
  let resolve: (settled: T) => void = () => undefined
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

async function mountButton(settings: DiscordSettings | null = SETTINGS) {
  useDiscordSettingsStore().settings = settings
  const wrapper = mount(DiscordSendLastResult)
  await flushPromises()
  return wrapper
}

type Wrapper = Awaited<ReturnType<typeof mountButton>>

function sendButton(wrapper: Wrapper) {
  return wrapper.get('button')
}

function isDisabled(wrapper: Wrapper): boolean {
  return sendButton(wrapper).attributes('disabled') !== undefined
}

function statusText(wrapper: Wrapper): string | null {
  const status = wrapper.find('[role="status"]')
  return status.exists() ? status.text() : null
}

function alertText(wrapper: Wrapper): string | null {
  const alert = wrapper.find('[role="alert"]')
  return alert.exists() ? alert.text() : null
}

async function pressSend(wrapper: Wrapper): Promise<void> {
  await sendButton(wrapper).trigger('click')
  await flushPromises()
}

async function passPoll(): Promise<void> {
  await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
  await flushPromises()
}

describe('DiscordSendLastResult', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    setActivePinia(createPinia())
    provideScrapeUseCases({
      getOptions,
      getScrape,
      getLatestScrape,
      startScrape,
      sendLatestScrapeToDiscord,
    })
    getLatestScrape.execute.mockResolvedValue(asDetail(SCRAPE))
    sendLatestScrapeToDiscord.execute.mockResolvedValue(SENDING)
    getScrape.execute.mockResolvedValue(asDetail(SENDING))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('is a plain button named Send last result that is on for a finished scrape', async () => {
    const wrapper = await mountButton()

    expect(sendButton(wrapper).text()).toBe('Send last result')
    expect(sendButton(wrapper).attributes('type')).toBe('button')
    expect(sendButton(wrapper).attributes('data-variant')).toBe('secondary')
    expect(isDisabled(wrapper)).toBe(false)
    expect(statusText(wrapper)).toBeNull()
    expect(alertText(wrapper)).toBeNull()
  })

  it('reads the latest scrape once when it shows', async () => {
    await mountButton()

    expect(getLatestScrape.execute).toHaveBeenCalledTimes(1)
  })

  it('is off when Discord is not configured', async () => {
    const wrapper = await mountButton({ ...SETTINGS, isConfigured: false, tokenHint: null })

    expect(isDisabled(wrapper)).toBe(true)
  })

  it('is off when no default channel is saved', async () => {
    const wrapper = await mountButton({ ...SETTINGS, defaultChannelId: null })

    expect(isDisabled(wrapper)).toBe(true)
  })

  it('is off when there is no scrape yet', async () => {
    getLatestScrape.execute.mockResolvedValue(null)
    const wrapper = await mountButton()

    expect(isDisabled(wrapper)).toBe(true)
  })

  it('is off until the latest scrape is known', async () => {
    getLatestScrape.execute.mockReturnValue(deferred<ScrapeDetail | null>().promise)
    const wrapper = await mountButton()

    expect(isDisabled(wrapper)).toBe(true)
  })

  it('is off when the latest scrape cannot be read', async () => {
    getLatestScrape.execute.mockRejectedValue(new Error('Scraper down'))
    const wrapper = await mountButton()

    expect(isDisabled(wrapper)).toBe(true)
  })

  it('is off when the latest scrape failed', async () => {
    getLatestScrape.execute.mockResolvedValue(asDetail({ ...SCRAPE, status: 'failed' }))
    const wrapper = await mountButton()

    expect(isDisabled(wrapper)).toBe(true)
  })

  it('is off while a scrape is going', async () => {
    getLatestScrape.execute.mockResolvedValue(asDetail({ ...SCRAPE, status: 'running' }))
    getScrape.execute.mockResolvedValue(asDetail({ ...SCRAPE, status: 'running' }))
    const wrapper = await mountButton()

    expect(isDisabled(wrapper)).toBe(true)
    expect(sendButton(wrapper).text()).toBe('Send last result')
  })

  it('is off while another Discord send is going', async () => {
    getLatestScrape.execute.mockResolvedValue(asDetail(SENDING))
    const wrapper = await mountButton()

    expect(isDisabled(wrapper)).toBe(true)
  })

  it.each([
    ['a partial scrape', { ...SCRAPE, status: 'partial' as const, errorCount: 1 }],
    ['a finished scrape with zero jobs', { ...SCRAPE, jobCount: 0 }],
    [
      'a scrape that was already sent',
      { ...SCRAPE, discordStatus: 'sent' as const, discordSent: 4 },
    ],
  ])('is on for %s', async (_name, latestRecord) => {
    getLatestScrape.execute.mockResolvedValue(asDetail(latestRecord))
    const wrapper = await mountButton()

    expect(isDisabled(wrapper)).toBe(false)
    expect(statusText(wrapper)).toBeNull()
  })

  it('asks once and reads Sending while the request is in flight', async () => {
    const pending = deferred<ScrapeRecord>()
    sendLatestScrapeToDiscord.execute.mockReturnValue(pending.promise)
    const wrapper = await mountButton()

    await pressSend(wrapper)

    expect(sendLatestScrapeToDiscord.execute).toHaveBeenCalledTimes(1)
    expect(sendButton(wrapper).text()).toBe('Sending')
    expect(isDisabled(wrapper)).toBe(true)
    expect(statusText(wrapper)).toBe('Sending the last result to Discord')

    pending.resolve(SENDING)
    await flushPromises()

    expect(sendButton(wrapper).text()).toBe('Sending')
    expect(isDisabled(wrapper)).toBe(true)
    expect(sendLatestScrapeToDiscord.execute).toHaveBeenCalledTimes(1)
  })

  it('says how many jobs were sent when the send settles', async () => {
    getScrape.execute
      .mockResolvedValueOnce(asDetail(SENDING))
      .mockResolvedValueOnce(asDetail({ ...SCRAPE, discordStatus: 'sent', discordSent: 4 }))
    const wrapper = await mountButton()
    await pressSend(wrapper)

    await passPoll()
    expect(statusText(wrapper)).toBe('Sending the last result to Discord')

    await passPoll()
    expect(statusText(wrapper)).toBe('Sent 4 to Discord')
    expect(alertText(wrapper)).toBeNull()
    expect(sendButton(wrapper).text()).toBe('Send last result')
    expect(isDisabled(wrapper)).toBe(false)
  })

  it('says how many were sent and failed on a partial send', async () => {
    getScrape.execute.mockResolvedValue(
      asDetail({ ...SCRAPE, discordStatus: 'partial', discordSent: 3, discordFailed: 1 }),
    )
    const wrapper = await mountButton()
    await pressSend(wrapper)

    await passPoll()

    expect(statusText(wrapper)).toBe('Sent 3, failed 1 on Discord')
    expect(alertText(wrapper)).toBeNull()
  })

  it('shows the error of the scrape record when the send failed', async () => {
    getScrape.execute.mockResolvedValue(
      asDetail({
        ...SCRAPE,
        discordStatus: 'failed',
        discordError: 'No default Discord channel is set.',
      }),
    )
    const wrapper = await mountButton()
    await pressSend(wrapper)

    await passPoll()

    expect(alertText(wrapper)).toBe('Discord failed: No default Discord channel is set.')
    expect(statusText(wrapper)).toBeNull()
    expect(isDisabled(wrapper)).toBe(false)
  })

  it('shows the message and does not poll when the request is refused', async () => {
    sendLatestScrapeToDiscord.execute.mockRejectedValue(new Error('A scrape is already running.'))
    const wrapper = await mountButton()

    await pressSend(wrapper)
    await passPoll()

    expect(alertText(wrapper)).toBe('A scrape is already running.')
    expect(statusText(wrapper)).toBeNull()
    expect(sendButton(wrapper).text()).toBe('Send last result')
    expect(getScrape.execute).not.toHaveBeenCalled()
  })

  it('clears the old outcome when it sends again', async () => {
    getScrape.execute.mockResolvedValueOnce(
      asDetail({ ...SCRAPE, discordStatus: 'sent', discordSent: 4 }),
    )
    const wrapper = await mountButton()
    await pressSend(wrapper)
    await passPoll()

    await pressSend(wrapper)

    expect(sendLatestScrapeToDiscord.execute).toHaveBeenCalledTimes(2)
    expect(statusText(wrapper)).toBe('Sending the last result to Discord')
  })

  it('stops polling once the send has settled', async () => {
    getScrape.execute
      .mockResolvedValueOnce(asDetail(SENDING))
      .mockResolvedValueOnce(asDetail({ ...SCRAPE, discordStatus: 'sent', discordSent: 4 }))
    const wrapper = await mountButton()
    await pressSend(wrapper)
    await passPoll()
    await passPoll()

    await passPoll()
    await passPoll()

    expect(getScrape.execute).toHaveBeenCalledTimes(2)
    expect(statusText(wrapper)).toBe('Sent 4 to Discord')
  })

  it('stops polling when it unmounts', async () => {
    const wrapper = await mountButton()
    await pressSend(wrapper)
    await passPoll()

    wrapper.unmount()
    await passPoll()
    await passPoll()

    expect(getScrape.execute).toHaveBeenCalledTimes(1)
    expect(useScrapeStore().isScraping).toBe(false)
  })

  it('does not start polling when the answer arrives after it unmounted', async () => {
    const pending = deferred<ScrapeRecord>()
    sendLatestScrapeToDiscord.execute.mockReturnValue(pending.promise)
    const wrapper = await mountButton()
    await pressSend(wrapper)

    wrapper.unmount()
    pending.resolve(SENDING)
    await flushPromises()
    await passPoll()

    expect(getScrape.execute).not.toHaveBeenCalled()
  })

  it('leaves a scrape that is still going alone when it unmounts', async () => {
    getLatestScrape.execute.mockResolvedValue(asDetail({ ...SCRAPE, status: 'running' }))
    getScrape.execute.mockResolvedValue(asDetail({ ...SCRAPE, status: 'running' }))
    const wrapper = await mountButton()

    wrapper.unmount()
    await passPoll()

    expect(getScrape.execute).toHaveBeenCalledTimes(1)
    expect(useScrapeStore().isScraping).toBe(true)
  })
})

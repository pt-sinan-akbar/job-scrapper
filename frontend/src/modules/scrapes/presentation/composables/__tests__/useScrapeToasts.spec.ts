import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import type { ScrapeDetail, ScrapeRecord } from '@/modules/scrapes/domain/entities/Scrape'
import { useScrapeToasts } from '@/modules/scrapes/presentation/composables/useScrapeToasts'
import { provideScrapeUseCases } from '@/modules/scrapes/presentation/stores/scrapeUseCases'
import {
  MAX_POLL_FAILURES,
  POLL_INTERVAL_MS,
  useScrapeStore,
} from '@/modules/scrapes/presentation/stores/useScrapeStore'

const toast = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }))
vi.mock('vue-sonner', () => ({ toast }))

const getOptions = { execute: vi.fn() }
const getScrape = { execute: vi.fn() }
const startScrape = { execute: vi.fn() }
const sendLatestScrapeToDiscord = { execute: vi.fn() }

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

const AppHost = defineComponent({
  setup() {
    useScrapeToasts()
    return () => null
  },
})

function asDetail(record: ScrapeRecord): ScrapeDetail {
  return { record, jobs: [], failures: [] }
}

function mountApp() {
  return mount(AppHost)
}

describe('useScrapeToasts', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    setActivePinia(createPinia())
    provideScrapeUseCases({
      getOptions,
      getScrape,
      getLatestScrape: { execute: vi.fn() },
      startScrape,
      sendLatestScrapeToDiscord,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it.each<[Partial<ScrapeRecord>, keyof typeof toast, string]>([
    [{}, 'success', 'Run finished with 4 jobs'],
    [{ status: 'partial', errorCount: 1 }, 'warning', 'Run finished with 4 jobs and 1 error'],
    [{ status: 'failed', error: 'Scraper crashed' }, 'error', 'Run failed: Scraper crashed'],
  ])('toasts when the scrape ends as %o', async (end, kind, message) => {
    startScrape.execute.mockResolvedValue({ ...SCRAPE, status: 'running' })
    getScrape.execute.mockResolvedValue(asDetail({ ...SCRAPE, ...end }))
    mountApp()

    await useScrapeStore().start(['django'], ['upwork'], false)
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

    expect(toast[kind]).toHaveBeenCalledWith(message)
  })

  it.each<[ScrapeRecord['discordStatus'], keyof typeof toast, string]>([
    ['sent', 'success', 'Sent 2 to Discord'],
    ['partial', 'warning', 'Sent 2, failed 1 on Discord'],
    ['failed', 'error', 'Discord failed: Missing access'],
  ])('toasts when sending ends as %s', async (final, kind, message) => {
    startScrape.execute.mockResolvedValue({
      ...SCRAPE,
      status: 'running',
      discordStatus: 'sending',
    })
    getScrape.execute.mockResolvedValue(
      asDetail({
        ...SCRAPE,
        discordStatus: final,
        discordSent: 2,
        discordFailed: final === 'partial' ? 1 : 0,
        discordError: final === 'failed' ? 'Missing access' : null,
      }),
    )
    mountApp()

    await useScrapeStore().start(['django'], ['upwork'], true)
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

    expect(toast[kind]).toHaveBeenCalledWith(message)
  })

  it('toasts the scrape end once and the Discord outcome once', async () => {
    startScrape.execute.mockResolvedValue({
      ...SCRAPE,
      status: 'running',
      discordStatus: 'sending',
    })
    getScrape.execute
      .mockResolvedValueOnce(asDetail({ ...SCRAPE, discordStatus: 'sending' }))
      .mockResolvedValueOnce(asDetail({ ...SCRAPE, discordStatus: 'sending' }))
      .mockResolvedValueOnce(asDetail({ ...SCRAPE, discordStatus: 'sent', discordSent: 4 }))
    mountApp()

    await useScrapeStore().start(['django'], ['upwork'], true)
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

    expect(toast.success.mock.calls).toEqual([['Run finished with 4 jobs'], ['Sent 4 to Discord']])
  })

  it('only toasts the scrape end for a scrape without a send', async () => {
    startScrape.execute.mockResolvedValue({ ...SCRAPE, status: 'running' })
    getScrape.execute.mockResolvedValue(asDetail(SCRAPE))
    mountApp()

    await useScrapeStore().start(['django'], ['upwork'], false)
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

    expect(toast.success.mock.calls).toEqual([['Run finished with 4 jobs']])
    expect(toast.warning).not.toHaveBeenCalled()
    expect(toast.error).not.toHaveBeenCalled()
  })
  it('toasts when a scrape cannot start', async () => {
    startScrape.execute.mockRejectedValue(new Error('A scrape is already running.'))
    mountApp()

    await useScrapeStore().start(['django'], ['upwork'], false)
    await vi.advanceTimersByTimeAsync(0)

    expect(toast.error).toHaveBeenCalledWith('A scrape is already running.')
  })

  it('toasts the same start error again on a second try', async () => {
    startScrape.execute.mockRejectedValue(new Error('A scrape is already running.'))
    mountApp()
    const store = useScrapeStore()

    await store.start(['django'], ['upwork'], false)
    await vi.advanceTimersByTimeAsync(0)
    await store.start(['django'], ['upwork'], false)
    await vi.advanceTimersByTimeAsync(0)

    expect(toast.error).toHaveBeenCalledTimes(2)
  })

  it('toasts when the scrape is lost after repeated failed polls', async () => {
    startScrape.execute.mockResolvedValue({ ...SCRAPE, status: 'running' })
    getScrape.execute.mockRejectedValue(new Error('timeout'))
    mountApp()

    await useScrapeStore().start(['django'], ['upwork'], false)
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * MAX_POLL_FAILURES)

    expect(toast.error).toHaveBeenCalledWith('Lost track of this run. Reload the page to check it.')
  })
})

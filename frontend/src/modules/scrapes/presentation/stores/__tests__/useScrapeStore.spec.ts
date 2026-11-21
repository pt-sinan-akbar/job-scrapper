import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ApiError } from '@/core/errors/ApiError'
import type {
  ScrapeDetail,
  ScrapeJob,
  ScrapeOptions,
  ScrapeRecord,
} from '@/modules/scrapes/domain/entities/Scrape'
import { provideScrapeUseCases } from '@/modules/scrapes/presentation/stores/scrapeUseCases'
import {
  MAX_DISCORD_WAIT_POLLS,
  MAX_POLL_FAILURES,
  POLL_INTERVAL_MS,
  useScrapeStore,
} from '@/modules/scrapes/presentation/stores/useScrapeStore'

const getOptions = { execute: vi.fn() }
const getScrape = { execute: vi.fn() }
const getLatestScrape = { execute: vi.fn() }
const startScrape = { execute: vi.fn() }
const sendLatestScrapeToDiscord = { execute: vi.fn() }

const OPTIONS: ScrapeOptions = {
  sites: [{ name: 'upwork', isEnabled: true }],
  isStale: false,
}

function record(
  status: ScrapeRecord['status'],
  discordStatus: ScrapeRecord['discordStatus'] = null,
): ScrapeRecord {
  return {
    id: 'run-1',
    status,
    keywords: ['django'],
    sites: ['upwork'],
    startedAt: '2026-11-01T10:00:00+00:00',
    finishedAt: null,
    jobCount: 0,
    errorCount: 0,
    error: null,
    discordStatus,
    discordSent: 0,
    discordFailed: 0,
    discordError: null,
  }
}

const JOB: ScrapeJob = {
  site: 'upwork',
  matchedKeyword: 'django',
  title: 'Django dev',
  company: 'Acme',
  location: 'Remote',
  url: 'https://example.com/1',
  postedAt: null,
  salary: null,
  workType: null,
  employmentType: null,
  experienceLevel: null,
  description: null,
  json: { site: 'upwork', matched_keyword: 'django', title: 'Django dev' },
}

function detail(
  status: ScrapeRecord['status'],
  discordStatus: ScrapeRecord['discordStatus'] = null,
  id = 'run-1',
): ScrapeDetail {
  const isDone = status !== 'running'
  return {
    record: { ...record(status, discordStatus), id },
    jobs: isDone ? [JOB] : [],
    failures: [],
  }
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve: (value: T) => void = () => undefined
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

describe('useScrapeStore', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useFakeTimers()
    setActivePinia(createPinia())
    provideScrapeUseCases({
      getOptions,
      getScrape,
      getLatestScrape,
      startScrape,
      sendLatestScrapeToDiscord,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads the scrape options', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    const store = useScrapeStore()

    await store.load()

    expect(store.status).toBe('ready')
    expect(store.options).toEqual(OPTIONS)
  })

  it('shows an error when options fail', async () => {
    getOptions.execute.mockRejectedValue(new Error('Scraper down'))
    const store = useScrapeStore()

    await store.load()

    expect(store.status).toBe('error')
    expect(store.errorMessage).toBe('Scraper down')
  })

  it('does not look for an active scrape on load', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    const store = useScrapeStore()

    await store.load()
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

    expect(store.isScraping).toBe(false)
    expect(getScrape.execute).not.toHaveBeenCalled()
  })

  it('asks for the options once while a load is already in flight', async () => {
    const pending = deferred<ScrapeOptions>()
    getOptions.execute.mockReturnValue(pending.promise)
    const store = useScrapeStore()

    void store.load()
    void store.load()
    pending.resolve(OPTIONS)
    await vi.advanceTimersByTimeAsync(0)

    expect(getOptions.execute).toHaveBeenCalledTimes(1)
    expect(store.status).toBe('ready')
  })

  it('keeps one poll loop when load runs again during a scrape', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    startScrape.execute.mockResolvedValue(record('running'))
    getScrape.execute.mockResolvedValue(detail('running'))
    const store = useScrapeStore()
    await store.start(['django'], ['upwork'], false)

    await store.load()
    await store.load()
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

    expect(store.isScraping).toBe(true)
    expect(getScrape.execute).toHaveBeenCalledTimes(3)
  })

  it('polls a started scrape until it ends', async () => {
    startScrape.execute.mockResolvedValue(record('running'))
    getScrape.execute
      .mockResolvedValueOnce(detail('running'))
      .mockResolvedValueOnce(detail('succeeded'))
    const store = useScrapeStore()

    await store.start(['django'], ['upwork'], false)
    expect(store.isScraping).toBe(true)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.isScraping).toBe(true)
    expect(store.scrapeOutcome).toBeNull()

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.isScraping).toBe(false)
    expect(store.scrapeOutcome?.status).toBe('succeeded')
    expect(getScrape.execute).toHaveBeenCalledTimes(2)
  })

  it('keeps the running record while a scrape runs and clears it when it ends', async () => {
    startScrape.execute.mockResolvedValue(record('running'))
    getScrape.execute
      .mockResolvedValueOnce(detail('running'))
      .mockResolvedValueOnce(detail('succeeded'))
    const store = useScrapeStore()

    await store.start(['django'], ['upwork'], false)
    expect(store.runningRecord?.keywords).toEqual(['django'])
    expect(store.runningRecord?.sites).toEqual(['upwork'])

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.runningRecord?.status).toBe('running')

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.runningRecord).toBeNull()
  })

  it('picks up the running record of a scrape found on load', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    getLatestScrape.execute.mockResolvedValue(detail('running'))
    getScrape.execute.mockResolvedValue(detail('running'))
    const store = useScrapeStore()

    await store.load()
    await store.loadLatest()

    expect(store.runningRecord?.id).toBe('run-1')
  })

  it('ignores a second start while a scrape is active', async () => {
    startScrape.execute.mockResolvedValue(record('running'))
    getScrape.execute.mockResolvedValue(detail('running'))
    const store = useScrapeStore()
    await store.start(['django'], ['upwork'], false)

    await store.start(['django'], ['upwork'], false)

    expect(startScrape.execute).toHaveBeenCalledTimes(1)
  })

  it('keeps the message when a scrape cannot start', async () => {
    startScrape.execute.mockRejectedValue(new Error('A scrape is already running.'))
    const store = useScrapeStore()

    await store.start(['django'], ['upwork'], false)

    expect(store.scrapeError?.message).toBe('A scrape is already running.')
    expect(store.isScraping).toBe(false)
  })

  it('keeps following a scrape through a failed poll', async () => {
    startScrape.execute.mockResolvedValue(record('running'))
    getScrape.execute
      .mockRejectedValueOnce(new Error('timeout'))
      .mockResolvedValueOnce(detail('succeeded'))
    const store = useScrapeStore()
    await store.start(['django'], ['upwork'], false)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.isScraping).toBe(true)
    expect(store.scrapeError).toBeNull()

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.isScraping).toBe(false)
    expect(store.scrapeOutcome?.status).toBe('succeeded')
  })

  it('gives up after repeated failed polls', async () => {
    startScrape.execute.mockResolvedValue(record('running'))
    getScrape.execute.mockRejectedValue(new Error('timeout'))
    const store = useScrapeStore()
    await store.start(['django'], ['upwork'], false)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * MAX_POLL_FAILURES)

    expect(store.isScraping).toBe(false)
    expect(store.scrapeError?.message).toContain('Lost track')
    expect(getScrape.execute).toHaveBeenCalledTimes(MAX_POLL_FAILURES)
  })

  it('counts only failures in a row', async () => {
    startScrape.execute.mockResolvedValue(record('running'))
    const failures = Array.from({ length: MAX_POLL_FAILURES - 1 }, () => new Error('timeout'))
    for (const failure of [...failures, null, ...failures]) {
      if (failure === null) {
        getScrape.execute.mockResolvedValueOnce(detail('running'))
      } else {
        getScrape.execute.mockRejectedValueOnce(failure)
      }
    }
    getScrape.execute.mockResolvedValueOnce(detail('succeeded'))
    const store = useScrapeStore()
    await store.start(['django'], ['upwork'], false)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * (MAX_POLL_FAILURES * 2))

    expect(store.scrapeOutcome?.status).toBe('succeeded')
  })

  describe('discord send', () => {
    it('passes the notify flag to the scrape', async () => {
      startScrape.execute.mockResolvedValue(record('running'))
      const store = useScrapeStore()

      await store.start(['django'], ['upwork'], true)

      expect(startScrape.execute).toHaveBeenCalledWith(['django'], ['upwork'], true)
    })

    it('keeps polling and stays running while the scrape is sending', async () => {
      startScrape.execute.mockResolvedValue(record('running', 'sending'))
      getScrape.execute
        .mockResolvedValueOnce(detail('succeeded', 'sending'))
        .mockResolvedValueOnce(detail('succeeded', 'sending'))
        .mockResolvedValueOnce(detail('succeeded', 'sent'))
      const store = useScrapeStore()
      await store.start(['django'], ['upwork'], true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isScraping).toBe(true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isScraping).toBe(true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isScraping).toBe(false)
      expect(getScrape.execute).toHaveBeenCalledTimes(3)
    })

    it('reports the scrape end once even while sending goes on', async () => {
      startScrape.execute.mockResolvedValue(record('running', 'sending'))
      const scrapeEnd = detail('succeeded', 'sending')
      getScrape.execute
        .mockResolvedValueOnce(scrapeEnd)
        .mockResolvedValueOnce(detail('succeeded', 'sending'))
        .mockResolvedValueOnce(detail('succeeded', 'sent'))
      const store = useScrapeStore()
      await store.start(['django'], ['upwork'], true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(store.scrapeOutcome).toStrictEqual(scrapeEnd.record)
    })

    it.each<[ScrapeRecord['discordStatus']]>([['sent'], ['partial'], ['failed']])(
      'reports the outcome when sending ends as %s',
      async (final) => {
        startScrape.execute.mockResolvedValue(record('running', 'sending'))
        getScrape.execute
          .mockResolvedValueOnce(detail('succeeded', 'sending'))
          .mockResolvedValueOnce(detail('succeeded', final))
        const store = useScrapeStore()
        await store.start(['django'], ['upwork'], true)
        expect(store.discordOutcome).toBeNull()

        await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2)

        expect(store.discordOutcome?.discordStatus).toBe(final)
      },
    )

    it('reports the outcome even when sending ends between two polls', async () => {
      startScrape.execute.mockResolvedValue(record('running', 'sending'))
      getScrape.execute.mockResolvedValueOnce(detail('succeeded', 'sent'))
      const store = useScrapeStore()
      await store.start(['django'], ['upwork'], true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(store.discordOutcome?.discordStatus).toBe('sent')
    })

    it('keeps polling a finished scrape while the asked for send has not started', async () => {
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute
        .mockResolvedValueOnce(detail('succeeded'))
        .mockResolvedValueOnce(detail('succeeded', 'sent'))
      const store = useScrapeStore()
      await store.start(['django'], ['upwork'], true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isScraping).toBe(true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isScraping).toBe(false)
      expect(store.discordOutcome?.discordStatus).toBe('sent')
    })

    it('stops waiting for a send that never starts after a few polls', async () => {
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockResolvedValue(detail('succeeded'))
      const store = useScrapeStore()
      await store.start(['django'], ['upwork'], true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * (MAX_DISCORD_WAIT_POLLS + 3))

      expect(store.isScraping).toBe(false)
      expect(store.discordOutcome).toBeNull()
      expect(getScrape.execute).toHaveBeenCalledTimes(MAX_DISCORD_WAIT_POLLS + 1)
    })

    it('forgets the expected send when it gives up on a scrape', async () => {
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockRejectedValue(new Error('timeout'))
      const store = useScrapeStore()
      await store.start(['django'], ['upwork'], true)
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * MAX_POLL_FAILURES)

      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockReset()
      getScrape.execute.mockResolvedValue(detail('succeeded', 'sent'))
      await store.start(['django'], ['upwork'], false)
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(store.discordOutcome).toBeNull()
    })

    it('does not report an outcome for a scrape without a send', async () => {
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockResolvedValueOnce(detail('succeeded'))
      const store = useScrapeStore()
      await store.start(['django'], ['upwork'], false)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(store.discordOutcome).toBeNull()
    })
  })
  describe('latest scrape', () => {
    it('loads the latest scrape detail', async () => {
      const latest = detail('succeeded', null, 'run-0')
      getLatestScrape.execute.mockResolvedValue(latest)
      const store = useScrapeStore()

      await store.loadLatest()

      expect(store.latestStatus).toBe('ready')
      expect(store.latestScrape).toStrictEqual(latest)
      expect(store.isResultsPending).toBe(false)
    })

    it('keeps no detail when there has been no scrape yet', async () => {
      getLatestScrape.execute.mockResolvedValue(null)
      const store = useScrapeStore()

      await store.loadLatest()

      expect(store.latestStatus).toBe('ready')
      expect(store.latestScrape).toBeNull()
      expect(store.isResultsPending).toBe(false)
    })

    it('is pending while the latest scrape loads for the first time', async () => {
      const pending = deferred<ScrapeDetail | null>()
      getLatestScrape.execute.mockReturnValue(pending.promise)
      const store = useScrapeStore()

      void store.loadLatest()

      expect(store.latestStatus).toBe('loading')
      expect(store.isResultsPending).toBe(true)

      pending.resolve(null)
      await vi.advanceTimersByTimeAsync(0)

      expect(store.isResultsPending).toBe(false)
    })

    it('keeps the shown detail and is not pending while it loads again', async () => {
      const latest = detail('succeeded', null, 'run-0')
      getLatestScrape.execute.mockResolvedValueOnce(latest)
      const store = useScrapeStore()
      await store.loadLatest()

      getLatestScrape.execute.mockReturnValueOnce(deferred<ScrapeDetail | null>().promise)
      void store.loadLatest()

      expect(store.latestScrape).toStrictEqual(latest)
      expect(store.isResultsPending).toBe(false)
    })

    it('asks once while a load of the latest scrape is in flight', async () => {
      const pending = deferred<ScrapeDetail | null>()
      getLatestScrape.execute.mockReturnValue(pending.promise)
      const store = useScrapeStore()

      void store.loadLatest()
      void store.loadLatest()
      pending.resolve(null)
      await vi.advanceTimersByTimeAsync(0)

      expect(getLatestScrape.execute).toHaveBeenCalledTimes(1)
    })

    it('keeps the message when the latest scrape cannot be loaded', async () => {
      getLatestScrape.execute.mockRejectedValue(new Error('Scraper down'))
      const store = useScrapeStore()

      await store.loadLatest()

      expect(store.latestStatus).toBe('error')
      expect(store.latestErrorMessage).toBe('Scraper down')
      expect(store.latestScrape).toBeNull()
    })

    it('is pending while a scrape started here is processing', async () => {
      getLatestScrape.execute.mockResolvedValue(detail('succeeded', null, 'run-0'))
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockResolvedValue(detail('running'))
      const store = useScrapeStore()
      await store.loadLatest()

      await store.start(['django'], ['upwork'], false)
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(store.isResultsPending).toBe(true)
    })

    it('shows the detail of a scrape started here once it ends', async () => {
      const finished = detail('partial')
      getLatestScrape.execute.mockResolvedValue(detail('succeeded', null, 'run-0'))
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockResolvedValueOnce(detail('running')).mockResolvedValueOnce(finished)
      const store = useScrapeStore()
      await store.loadLatest()
      await store.start(['django'], ['upwork'], false)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2)

      expect(store.latestScrape).toStrictEqual(finished)
      expect(store.isResultsPending).toBe(false)
      expect(store.scrapeOutcome).toStrictEqual(finished.record)
    })

    it('shows the results while the Discord send goes on after the scrape ends', async () => {
      startScrape.execute.mockResolvedValue(record('running', 'sending'))
      getScrape.execute.mockResolvedValue(detail('succeeded', 'sending'))
      const store = useScrapeStore()
      await store.start(['django'], ['upwork'], true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(store.isScraping).toBe(true)
      expect(store.isResultsPending).toBe(false)
      expect(store.latestScrape?.record.status).toBe('succeeded')
    })

    it('follows a latest scrape that is still going until it ends', async () => {
      const finished = detail('succeeded', null, 'run-0')
      getLatestScrape.execute.mockResolvedValue(detail('running', null, 'run-0'))
      getScrape.execute
        .mockResolvedValueOnce(detail('running', null, 'run-0'))
        .mockResolvedValueOnce(finished)
      const store = useScrapeStore()

      await store.loadLatest()
      expect(store.isScraping).toBe(true)
      expect(store.isResultsPending).toBe(true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isScraping).toBe(true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(getScrape.execute).toHaveBeenCalledWith('run-0')
      expect(store.isScraping).toBe(false)
      expect(store.isResultsPending).toBe(false)
      expect(store.latestScrape).toStrictEqual(finished)
      expect(store.scrapeOutcome).toStrictEqual(finished.record)
    })

    it('follows a latest scrape whose Discord send is going and reports the send', async () => {
      getLatestScrape.execute.mockResolvedValue(detail('succeeded', 'sending', 'run-0'))
      getScrape.execute.mockResolvedValueOnce(detail('succeeded', 'sent', 'run-0'))
      const store = useScrapeStore()

      await store.loadLatest()
      expect(store.isScraping).toBe(true)
      expect(store.isResultsPending).toBe(false)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isScraping).toBe(false)
      expect(store.discordOutcome?.discordStatus).toBe('sent')
    })

    it('stops following a latest scrape the scraper no longer has and shows it as is', async () => {
      const running = detail('running', null, 'run-0')
      getLatestScrape.execute.mockResolvedValue(running)
      getScrape.execute.mockRejectedValue(new ApiError(404, 'Not found.'))
      const store = useScrapeStore()
      await store.loadLatest()

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(getScrape.execute).toHaveBeenCalledTimes(1)
      expect(store.isScraping).toBe(false)
      expect(store.isResultsPending).toBe(false)
      expect(store.isResultsLost).toBe(false)
      expect(store.latestScrape).toStrictEqual(running)
      expect(store.scrapeError).toBeNull()
    })

    it('gives up on a followed latest scrape after repeated failed polls', async () => {
      getLatestScrape.execute.mockResolvedValue(detail('running', null, 'run-0'))
      getScrape.execute.mockRejectedValue(new Error('timeout'))
      const store = useScrapeStore()
      await store.loadLatest()

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * MAX_POLL_FAILURES)

      expect(store.isScraping).toBe(false)
      expect(store.isResultsPending).toBe(false)
      expect(store.isResultsLost).toBe(true)
    })

    it('does not follow a finished latest scrape', async () => {
      getLatestScrape.execute.mockResolvedValue(detail('succeeded', 'sent', 'run-0'))
      const store = useScrapeStore()

      await store.loadLatest()
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(store.isScraping).toBe(false)
      expect(getScrape.execute).not.toHaveBeenCalled()
    })

    it('marks the results lost instead of showing the older scrape when a scrape is lost', async () => {
      getLatestScrape.execute.mockResolvedValue(detail('succeeded', null, 'run-0'))
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockRejectedValue(new Error('timeout'))
      const store = useScrapeStore()
      await store.loadLatest()
      await store.start(['django'], ['upwork'], false)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * MAX_POLL_FAILURES)

      expect(store.isResultsLost).toBe(true)
      expect(store.isResultsPending).toBe(false)
    })

    it('marks the results lost when a scrape started here is gone', async () => {
      getLatestScrape.execute.mockResolvedValue(detail('succeeded', null, 'run-0'))
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockRejectedValue(new ApiError(404, 'Not found.'))
      const store = useScrapeStore()
      await store.loadLatest()
      await store.start(['django'], ['upwork'], false)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(getScrape.execute).toHaveBeenCalledTimes(1)
      expect(store.isScraping).toBe(false)
      expect(store.isResultsLost).toBe(true)
    })

    it('clears the lost mark when a new scrape starts', async () => {
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockRejectedValue(new Error('timeout'))
      const store = useScrapeStore()
      await store.start(['django'], ['upwork'], false)
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * MAX_POLL_FAILURES)

      getScrape.execute.mockReset()
      getScrape.execute.mockResolvedValue(detail('running'))
      await store.start(['django'], ['upwork'], false)

      expect(store.isResultsLost).toBe(false)
      expect(store.isResultsPending).toBe(true)
    })

    it('clears the lost mark on reset', async () => {
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockRejectedValue(new Error('timeout'))
      const store = useScrapeStore()
      await store.start(['django'], ['upwork'], false)
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * MAX_POLL_FAILURES)

      store.reset()

      expect(store.isResultsLost).toBe(false)
    })

    it('keeps the detail of a scrape that ended here over an older latest load', async () => {
      const pending = deferred<ScrapeDetail | null>()
      const finished = detail('succeeded')
      getLatestScrape.execute.mockReturnValue(pending.promise)
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockResolvedValue(finished)
      const store = useScrapeStore()
      void store.loadLatest()
      await store.start(['django'], ['upwork'], false)
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      pending.resolve(detail('running'))
      await vi.advanceTimersByTimeAsync(0)

      expect(store.latestScrape).toStrictEqual(finished)
      expect(store.latestStatus).toBe('ready')
      expect(store.isScraping).toBe(false)
    })

    it('clears the latest scrape on reset and ignores a load in flight', async () => {
      getLatestScrape.execute.mockResolvedValueOnce(detail('succeeded', null, 'run-0'))
      const store = useScrapeStore()
      await store.loadLatest()
      const pending = deferred<ScrapeDetail | null>()
      getLatestScrape.execute.mockReturnValueOnce(pending.promise)
      void store.loadLatest()

      store.reset()
      pending.resolve(detail('succeeded', null, 'run-9'))
      await vi.advanceTimersByTimeAsync(0)

      expect(store.latestScrape).toBeNull()
      expect(store.latestStatus).toBe('idle')
      expect(store.latestErrorMessage).toBeNull()
      expect(store.isResultsPending).toBe(false)
    })
  })

  describe('reset', () => {
    it('stops polling and clears the scrape state', async () => {
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockResolvedValue(detail('running'))
      const store = useScrapeStore()
      await store.start(['django'], ['upwork'], true)

      store.reset()
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(getScrape.execute).not.toHaveBeenCalled()
      expect(store.isScraping).toBe(false)
      expect(store.scrapeError).toBeNull()
    })

    it('clears the outcomes, options and errors', async () => {
      getOptions.execute.mockResolvedValue(OPTIONS)
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockResolvedValue(detail('succeeded', 'sent'))
      const store = useScrapeStore()
      await store.load()
      await store.start(['django'], ['upwork'], true)
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      store.reset()

      expect(store.status).toBe('idle')
      expect(store.options).toBeNull()
      expect(store.scrapeOutcome).toBeNull()
      expect(store.discordOutcome).toBeNull()
    })

    it('ignores a poll that was in flight when it reset', async () => {
      const pending = deferred<ScrapeDetail>()
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockReturnValueOnce(pending.promise).mockResolvedValue(detail('running'))
      const store = useScrapeStore()
      await store.start(['django'], ['upwork'], false)
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      store.reset()
      pending.resolve(detail('succeeded'))
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(getScrape.execute).toHaveBeenCalledTimes(1)
      expect(store.scrapeOutcome).toBeNull()
      expect(store.isScraping).toBe(false)
    })

    it('ignores a start that was in flight when it reset', async () => {
      const pending = deferred<ScrapeRecord>()
      startScrape.execute.mockReturnValue(pending.promise)
      const store = useScrapeStore()
      const starting = store.start(['django'], ['upwork'], false)

      store.reset()
      pending.resolve(record('running'))
      await starting
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(store.isScraping).toBe(false)
      expect(getScrape.execute).not.toHaveBeenCalled()
    })

    it('lets a new scrape start after a reset', async () => {
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockResolvedValue(detail('running'))
      const store = useScrapeStore()
      await store.start(['django'], ['upwork'], false)

      store.reset()
      await store.start(['django'], ['upwork'], false)

      expect(startScrape.execute).toHaveBeenCalledTimes(2)
      expect(store.isScraping).toBe(true)
    })
  })

  describe('send latest to discord', () => {
    function sentRecord(sent: number, failed = 0): ScrapeRecord {
      const status = failed > 0 ? 'partial' : 'sent'
      return { ...record('succeeded', status), discordSent: sent, discordFailed: failed }
    }

    function sentDetail(sent: number, failed = 0): ScrapeDetail {
      return { ...detail('succeeded'), record: sentRecord(sent, failed) }
    }

    it('asks once and follows the scrape until the send settles', async () => {
      sendLatestScrapeToDiscord.execute.mockResolvedValue(record('succeeded', 'sending'))
      getScrape.execute
        .mockResolvedValueOnce(detail('succeeded', 'sending'))
        .mockResolvedValueOnce(sentDetail(4))
      const store = useScrapeStore()

      await store.sendLatestToDiscord()

      expect(store.isSendingLatest).toBe(true)
      expect(store.isScraping).toBe(true)
      expect(store.latestSendOutcome).toBeNull()

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isSendingLatest).toBe(true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isSendingLatest).toBe(false)
      expect(store.isScraping).toBe(false)
      expect(store.latestSendOutcome?.discordStatus).toBe('sent')
      expect(store.latestSendOutcome?.discordSent).toBe(4)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)
      expect(sendLatestScrapeToDiscord.execute).toHaveBeenCalledTimes(1)
      expect(getScrape.execute).toHaveBeenCalledTimes(2)
      expect(getScrape.execute).toHaveBeenCalledWith('run-1')
    })

    it('is sending while the request is in flight', async () => {
      const pending = deferred<ScrapeRecord>()
      sendLatestScrapeToDiscord.execute.mockReturnValue(pending.promise)
      const store = useScrapeStore()

      const sending = store.sendLatestToDiscord()

      expect(store.isSendingLatest).toBe(true)

      pending.resolve(record('succeeded', 'sending'))
      await sending

      expect(store.isSendingLatest).toBe(true)
    })

    it('ignores a second press while the first is in flight or followed', async () => {
      const pending = deferred<ScrapeRecord>()
      sendLatestScrapeToDiscord.execute.mockReturnValue(pending.promise)
      getScrape.execute.mockResolvedValue(detail('succeeded', 'sending'))
      const store = useScrapeStore()
      const sending = store.sendLatestToDiscord()

      await store.sendLatestToDiscord()
      pending.resolve(record('succeeded', 'sending'))
      await sending
      await store.sendLatestToDiscord()

      expect(sendLatestScrapeToDiscord.execute).toHaveBeenCalledTimes(1)
    })

    it('does not ask while a scrape is active', async () => {
      startScrape.execute.mockResolvedValue(record('running'))
      const store = useScrapeStore()
      await store.start(['django'], ['upwork'], false)

      await store.sendLatestToDiscord()

      expect(sendLatestScrapeToDiscord.execute).not.toHaveBeenCalled()
      expect(store.isSendingLatest).toBe(false)
    })

    it('shows the sending status on the shown scrape right away', async () => {
      getLatestScrape.execute.mockResolvedValue(detail('succeeded'))
      sendLatestScrapeToDiscord.execute.mockResolvedValue(record('succeeded', 'sending'))
      const store = useScrapeStore()
      await store.loadLatest()

      await store.sendLatestToDiscord()

      expect(store.latestScrape?.record.discordStatus).toBe('sending')
      expect(store.latestScrape?.jobs).toEqual([JOB])
    })

    it('keeps the outcome of a partial send', async () => {
      sendLatestScrapeToDiscord.execute.mockResolvedValue(record('succeeded', 'sending'))
      getScrape.execute.mockResolvedValue(sentDetail(3, 2))
      const store = useScrapeStore()
      await store.sendLatestToDiscord()

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(store.latestSendOutcome?.discordStatus).toBe('partial')
      expect(store.latestSendOutcome?.discordSent).toBe(3)
      expect(store.latestSendOutcome?.discordFailed).toBe(2)
    })

    it('keeps the error of a failed send', async () => {
      sendLatestScrapeToDiscord.execute.mockResolvedValue(record('succeeded', 'sending'))
      getScrape.execute.mockResolvedValue({
        ...detail('succeeded'),
        record: { ...record('succeeded', 'failed'), discordError: 'No default Discord channel' },
      })
      const store = useScrapeStore()
      await store.sendLatestToDiscord()

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(store.latestSendOutcome?.discordStatus).toBe('failed')
      expect(store.latestSendOutcome?.discordError).toBe('No default Discord channel')
    })

    it('reports neither a scrape end nor a Discord toast for the send', async () => {
      sendLatestScrapeToDiscord.execute.mockResolvedValue(record('succeeded', 'sending'))
      getScrape.execute.mockResolvedValue(sentDetail(4))
      const store = useScrapeStore()
      await store.sendLatestToDiscord()

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(store.scrapeOutcome).toBeNull()
      expect(store.discordOutcome).toBeNull()
    })

    it('keeps the message when the send is refused and does not poll', async () => {
      sendLatestScrapeToDiscord.execute.mockRejectedValue(new Error('A scrape is already running.'))
      const store = useScrapeStore()

      await store.sendLatestToDiscord()
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(store.latestSendError).toBe('A scrape is already running.')
      expect(store.isSendingLatest).toBe(false)
      expect(store.isScraping).toBe(false)
      expect(store.scrapeError).toBeNull()
      expect(getScrape.execute).not.toHaveBeenCalled()
    })

    it('clears the old error and outcome when it sends again', async () => {
      sendLatestScrapeToDiscord.execute
        .mockRejectedValueOnce(new Error('A scrape is already running.'))
        .mockResolvedValueOnce(record('succeeded', 'sending'))
      const store = useScrapeStore()
      await store.sendLatestToDiscord()

      await store.sendLatestToDiscord()

      expect(store.latestSendError).toBeNull()
      expect(store.latestSendOutcome).toBeNull()
    })

    it('stops polling when the send is stopped', async () => {
      sendLatestScrapeToDiscord.execute.mockResolvedValue(record('succeeded', 'sending'))
      getScrape.execute.mockResolvedValue(detail('succeeded', 'sending'))
      const store = useScrapeStore()
      await store.sendLatestToDiscord()
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      store.stopLatestSend()
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(getScrape.execute).toHaveBeenCalledTimes(1)
      expect(store.isScraping).toBe(false)
      expect(store.isSendingLatest).toBe(false)
    })

    it('does not start polling when the answer arrives after the send was stopped', async () => {
      const pending = deferred<ScrapeRecord>()
      sendLatestScrapeToDiscord.execute.mockReturnValue(pending.promise)
      const store = useScrapeStore()
      const sending = store.sendLatestToDiscord()

      store.stopLatestSend()
      pending.resolve(record('succeeded', 'sending'))
      await sending
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(store.isSendingLatest).toBe(false)
      expect(store.isScraping).toBe(false)
      expect(getScrape.execute).not.toHaveBeenCalled()
    })

    it('keeps following a normal scrape when the send is stopped', async () => {
      startScrape.execute.mockResolvedValue(record('running'))
      getScrape.execute.mockResolvedValue(detail('running'))
      const store = useScrapeStore()
      await store.start(['django'], ['upwork'], false)

      store.stopLatestSend()
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(store.isScraping).toBe(true)
      expect(getScrape.execute).toHaveBeenCalledTimes(1)
    })

    it('reports the send as a normal Discord outcome once it is followed again', async () => {
      sendLatestScrapeToDiscord.execute.mockResolvedValue(record('succeeded', 'sending'))
      getLatestScrape.execute.mockResolvedValue(detail('succeeded', 'sending'))
      getScrape.execute.mockResolvedValue(sentDetail(4))
      const store = useScrapeStore()
      await store.sendLatestToDiscord()
      store.stopLatestSend()

      await store.loadLatest()
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(store.discordOutcome?.discordStatus).toBe('sent')
      expect(store.scrapeOutcome).toBeNull()
      expect(store.latestSendOutcome).toBeNull()
    })

    it('clears the send state on reset and ignores an answer in flight', async () => {
      const pending = deferred<ScrapeRecord>()
      sendLatestScrapeToDiscord.execute.mockReturnValue(pending.promise)
      const store = useScrapeStore()
      const sending = store.sendLatestToDiscord()

      store.reset()
      pending.resolve(record('succeeded', 'sending'))
      await sending
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(store.isSendingLatest).toBe(false)
      expect(store.latestSendError).toBeNull()
      expect(getScrape.execute).not.toHaveBeenCalled()
    })
  })
})

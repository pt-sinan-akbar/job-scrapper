import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { RunOptions, RunRecord } from '@/modules/runs/domain/entities/Run'
import { provideRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'
import {
  MAX_DISCORD_WAIT_POLLS,
  MAX_POLL_FAILURES,
  POLL_INTERVAL_MS,
  useRunStore,
} from '@/modules/runs/presentation/stores/useRunStore'

const getOptions = { execute: vi.fn() }
const getRun = { execute: vi.fn() }
const startRun = { execute: vi.fn() }

const OPTIONS: RunOptions = {
  keywords: ['django'],
  sites: [{ name: 'upwork', isEnabled: true }],
  isStale: false,
}

function record(
  status: RunRecord['status'],
  discordStatus: RunRecord['discordStatus'] = null,
): RunRecord {
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

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve: (value: T) => void = () => undefined
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

describe('useRunStore', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useFakeTimers()
    setActivePinia(createPinia())
    provideRunUseCases({ getOptions, getRun, startRun })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads the run options', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    const store = useRunStore()

    await store.load()

    expect(store.status).toBe('ready')
    expect(store.options?.keywords).toEqual(['django'])
  })

  it('shows an error when options fail', async () => {
    getOptions.execute.mockRejectedValue(new Error('Scraper down'))
    const store = useRunStore()

    await store.load()

    expect(store.status).toBe('error')
    expect(store.errorMessage).toBe('Scraper down')
  })

  it('does not look for an active run on load', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    const store = useRunStore()

    await store.load()
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

    expect(store.isRunning).toBe(false)
    expect(getRun.execute).not.toHaveBeenCalled()
  })

  it('asks for the options once while a load is already in flight', async () => {
    const pending = deferred<RunOptions>()
    getOptions.execute.mockReturnValue(pending.promise)
    const store = useRunStore()

    void store.load()
    void store.load()
    pending.resolve(OPTIONS)
    await vi.advanceTimersByTimeAsync(0)

    expect(getOptions.execute).toHaveBeenCalledTimes(1)
    expect(store.status).toBe('ready')
  })

  it('keeps one poll loop when load runs again during a run', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    startRun.execute.mockResolvedValue(record('running'))
    getRun.execute.mockResolvedValue(record('running'))
    const store = useRunStore()
    await store.start(['django'], ['upwork'], false)

    await store.load()
    await store.load()
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

    expect(store.isRunning).toBe(true)
    expect(getRun.execute).toHaveBeenCalledTimes(3)
  })

  it('polls a started run until it ends', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    getRun.execute
      .mockResolvedValueOnce(record('running'))
      .mockResolvedValueOnce(record('succeeded'))
    const store = useRunStore()

    await store.start(['django'], ['upwork'], false)
    expect(store.isRunning).toBe(true)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.isRunning).toBe(true)
    expect(store.runOutcome).toBeNull()

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.isRunning).toBe(false)
    expect(store.runOutcome?.status).toBe('succeeded')
    expect(getRun.execute).toHaveBeenCalledTimes(2)
  })

  it('ignores a second start while a run is active', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    getRun.execute.mockResolvedValue(record('running'))
    const store = useRunStore()
    await store.start(['django'], ['upwork'], false)

    await store.start(['django'], ['upwork'], false)

    expect(startRun.execute).toHaveBeenCalledTimes(1)
  })

  it('keeps the message when a run cannot start', async () => {
    startRun.execute.mockRejectedValue(new Error('A scrape is already running.'))
    const store = useRunStore()

    await store.start(['django'], ['upwork'], false)

    expect(store.runError?.message).toBe('A scrape is already running.')
    expect(store.isRunning).toBe(false)
  })

  it('keeps following a run through a failed poll', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    getRun.execute
      .mockRejectedValueOnce(new Error('timeout'))
      .mockResolvedValueOnce(record('succeeded'))
    const store = useRunStore()
    await store.start(['django'], ['upwork'], false)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.isRunning).toBe(true)
    expect(store.runError).toBeNull()

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.isRunning).toBe(false)
    expect(store.runOutcome?.status).toBe('succeeded')
  })

  it('gives up after repeated failed polls', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    getRun.execute.mockRejectedValue(new Error('timeout'))
    const store = useRunStore()
    await store.start(['django'], ['upwork'], false)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * MAX_POLL_FAILURES)

    expect(store.isRunning).toBe(false)
    expect(store.runError?.message).toContain('Lost track')
    expect(getRun.execute).toHaveBeenCalledTimes(MAX_POLL_FAILURES)
  })

  it('counts only failures in a row', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    const failures = Array.from({ length: MAX_POLL_FAILURES - 1 }, () => new Error('timeout'))
    for (const failure of [...failures, null, ...failures]) {
      if (failure === null) {
        getRun.execute.mockResolvedValueOnce(record('running'))
      } else {
        getRun.execute.mockRejectedValueOnce(failure)
      }
    }
    getRun.execute.mockResolvedValueOnce(record('succeeded'))
    const store = useRunStore()
    await store.start(['django'], ['upwork'], false)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * (MAX_POLL_FAILURES * 2))

    expect(store.runOutcome?.status).toBe('succeeded')
  })

  describe('discord send', () => {
    it('passes the notify flag to the run', async () => {
      startRun.execute.mockResolvedValue(record('running'))
      const store = useRunStore()

      await store.start(['django'], ['upwork'], true)

      expect(startRun.execute).toHaveBeenCalledWith(['django'], ['upwork'], true)
    })

    it('keeps polling and stays running while the run is sending', async () => {
      startRun.execute.mockResolvedValue(record('running', 'sending'))
      getRun.execute
        .mockResolvedValueOnce(record('succeeded', 'sending'))
        .mockResolvedValueOnce(record('succeeded', 'sending'))
        .mockResolvedValueOnce(record('succeeded', 'sent'))
      const store = useRunStore()
      await store.start(['django'], ['upwork'], true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isRunning).toBe(true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isRunning).toBe(true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isRunning).toBe(false)
      expect(getRun.execute).toHaveBeenCalledTimes(3)
    })

    it('reports the scrape end once even while sending goes on', async () => {
      startRun.execute.mockResolvedValue(record('running', 'sending'))
      const scrapeEnd = record('succeeded', 'sending')
      getRun.execute
        .mockResolvedValueOnce(scrapeEnd)
        .mockResolvedValueOnce(record('succeeded', 'sending'))
        .mockResolvedValueOnce(record('succeeded', 'sent'))
      const store = useRunStore()
      await store.start(['django'], ['upwork'], true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(store.runOutcome).toStrictEqual(scrapeEnd)
    })

    it.each<[RunRecord['discordStatus']]>([['sent'], ['partial'], ['failed']])(
      'reports the outcome when sending ends as %s',
      async (final) => {
        startRun.execute.mockResolvedValue(record('running', 'sending'))
        getRun.execute
          .mockResolvedValueOnce(record('succeeded', 'sending'))
          .mockResolvedValueOnce(record('succeeded', final))
        const store = useRunStore()
        await store.start(['django'], ['upwork'], true)
        expect(store.discordOutcome).toBeNull()

        await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2)

        expect(store.discordOutcome?.discordStatus).toBe(final)
      },
    )

    it('reports the outcome even when sending ends between two polls', async () => {
      startRun.execute.mockResolvedValue(record('running', 'sending'))
      getRun.execute.mockResolvedValueOnce(record('succeeded', 'sent'))
      const store = useRunStore()
      await store.start(['django'], ['upwork'], true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(store.discordOutcome?.discordStatus).toBe('sent')
    })

    it('keeps polling a finished run while the asked for send has not started', async () => {
      startRun.execute.mockResolvedValue(record('running'))
      getRun.execute
        .mockResolvedValueOnce(record('succeeded'))
        .mockResolvedValueOnce(record('succeeded', 'sent'))
      const store = useRunStore()
      await store.start(['django'], ['upwork'], true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isRunning).toBe(true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isRunning).toBe(false)
      expect(store.discordOutcome?.discordStatus).toBe('sent')
    })

    it('stops waiting for a send that never starts after a few polls', async () => {
      startRun.execute.mockResolvedValue(record('running'))
      getRun.execute.mockResolvedValue(record('succeeded'))
      const store = useRunStore()
      await store.start(['django'], ['upwork'], true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * (MAX_DISCORD_WAIT_POLLS + 3))

      expect(store.isRunning).toBe(false)
      expect(store.discordOutcome).toBeNull()
      expect(getRun.execute).toHaveBeenCalledTimes(MAX_DISCORD_WAIT_POLLS + 1)
    })

    it('forgets the expected send when it gives up on a run', async () => {
      startRun.execute.mockResolvedValue(record('running'))
      getRun.execute.mockRejectedValue(new Error('timeout'))
      const store = useRunStore()
      await store.start(['django'], ['upwork'], true)
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * MAX_POLL_FAILURES)

      startRun.execute.mockResolvedValue(record('running'))
      getRun.execute.mockReset()
      getRun.execute.mockResolvedValue(record('succeeded', 'sent'))
      await store.start(['django'], ['upwork'], false)
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(store.discordOutcome).toBeNull()
    })

    it('does not report an outcome for a run without a send', async () => {
      startRun.execute.mockResolvedValue(record('running'))
      getRun.execute.mockResolvedValueOnce(record('succeeded'))
      const store = useRunStore()
      await store.start(['django'], ['upwork'], false)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(store.discordOutcome).toBeNull()
    })
  })
  describe('reset', () => {
    it('stops polling and clears the run state', async () => {
      startRun.execute.mockResolvedValue(record('running'))
      getRun.execute.mockResolvedValue(record('running'))
      const store = useRunStore()
      await store.start(['django'], ['upwork'], true)

      store.reset()
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(getRun.execute).not.toHaveBeenCalled()
      expect(store.isRunning).toBe(false)
      expect(store.runError).toBeNull()
    })

    it('clears the outcomes, options and errors', async () => {
      getOptions.execute.mockResolvedValue(OPTIONS)
      startRun.execute.mockResolvedValue(record('running'))
      getRun.execute.mockResolvedValue(record('succeeded', 'sent'))
      const store = useRunStore()
      await store.load()
      await store.start(['django'], ['upwork'], true)
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      store.reset()

      expect(store.status).toBe('idle')
      expect(store.options).toBeNull()
      expect(store.runOutcome).toBeNull()
      expect(store.discordOutcome).toBeNull()
    })

    it('ignores a poll that was in flight when it reset', async () => {
      const pending = deferred<RunRecord>()
      startRun.execute.mockResolvedValue(record('running'))
      getRun.execute.mockReturnValueOnce(pending.promise).mockResolvedValue(record('running'))
      const store = useRunStore()
      await store.start(['django'], ['upwork'], false)
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      store.reset()
      pending.resolve(record('succeeded'))
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(getRun.execute).toHaveBeenCalledTimes(1)
      expect(store.runOutcome).toBeNull()
      expect(store.isRunning).toBe(false)
    })

    it('ignores a start that was in flight when it reset', async () => {
      const pending = deferred<RunRecord>()
      startRun.execute.mockReturnValue(pending.promise)
      const store = useRunStore()
      const starting = store.start(['django'], ['upwork'], false)

      store.reset()
      pending.resolve(record('running'))
      await starting
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(store.isRunning).toBe(false)
      expect(getRun.execute).not.toHaveBeenCalled()
    })

    it('lets a new run start after a reset', async () => {
      startRun.execute.mockResolvedValue(record('running'))
      getRun.execute.mockResolvedValue(record('running'))
      const store = useRunStore()
      await store.start(['django'], ['upwork'], false)

      store.reset()
      await store.start(['django'], ['upwork'], false)

      expect(startRun.execute).toHaveBeenCalledTimes(2)
      expect(store.isRunning).toBe(true)
    })
  })
})

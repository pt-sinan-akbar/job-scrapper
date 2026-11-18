import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import type { RunRecord } from '@/modules/runs/domain/entities/Run'
import { useRunToasts } from '@/modules/runs/presentation/composables/useRunToasts'
import { provideRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'
import {
  MAX_POLL_FAILURES,
  POLL_INTERVAL_MS,
  useRunStore,
} from '@/modules/runs/presentation/stores/useRunStore'

const toast = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }))
vi.mock('vue-sonner', () => ({ toast }))

const getOptions = { execute: vi.fn() }
const getRun = { execute: vi.fn() }
const startRun = { execute: vi.fn() }

const RUN: RunRecord = {
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
    useRunToasts()
    return () => null
  },
})

function mountApp() {
  return mount(AppHost)
}

describe('useRunToasts', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    setActivePinia(createPinia())
    provideRunUseCases({ getOptions, getRun, startRun })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it.each<[Partial<RunRecord>, keyof typeof toast, string]>([
    [{}, 'success', 'Run finished with 4 jobs'],
    [{ status: 'partial', errorCount: 1 }, 'warning', 'Run finished with 4 jobs and 1 error'],
    [{ status: 'failed', error: 'Scraper crashed' }, 'error', 'Run failed: Scraper crashed'],
  ])('toasts when the run ends as %o', async (end, kind, message) => {
    startRun.execute.mockResolvedValue({ ...RUN, status: 'running' })
    getRun.execute.mockResolvedValue({ ...RUN, ...end })
    mountApp()

    await useRunStore().start(['django'], ['upwork'], false)
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

    expect(toast[kind]).toHaveBeenCalledWith(message)
  })

  it.each<[RunRecord['discordStatus'], keyof typeof toast, string]>([
    ['sent', 'success', 'Sent 2 to Discord'],
    ['partial', 'warning', 'Sent 2, failed 1 on Discord'],
    ['failed', 'error', 'Discord failed: Missing access'],
  ])('toasts when sending ends as %s', async (final, kind, message) => {
    startRun.execute.mockResolvedValue({ ...RUN, status: 'running', discordStatus: 'sending' })
    getRun.execute.mockResolvedValue({
      ...RUN,
      discordStatus: final,
      discordSent: 2,
      discordFailed: final === 'partial' ? 1 : 0,
      discordError: final === 'failed' ? 'Missing access' : null,
    })
    mountApp()

    await useRunStore().start(['django'], ['upwork'], true)
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

    expect(toast[kind]).toHaveBeenCalledWith(message)
  })

  it('toasts the run end once and the Discord outcome once', async () => {
    startRun.execute.mockResolvedValue({ ...RUN, status: 'running', discordStatus: 'sending' })
    getRun.execute
      .mockResolvedValueOnce({ ...RUN, discordStatus: 'sending' })
      .mockResolvedValueOnce({ ...RUN, discordStatus: 'sending' })
      .mockResolvedValueOnce({ ...RUN, discordStatus: 'sent', discordSent: 4 })
    mountApp()

    await useRunStore().start(['django'], ['upwork'], true)
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

    expect(toast.success.mock.calls).toEqual([['Run finished with 4 jobs'], ['Sent 4 to Discord']])
  })

  it('only toasts the run end for a run without a send', async () => {
    startRun.execute.mockResolvedValue({ ...RUN, status: 'running' })
    getRun.execute.mockResolvedValue(RUN)
    mountApp()

    await useRunStore().start(['django'], ['upwork'], false)
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

    expect(toast.success.mock.calls).toEqual([['Run finished with 4 jobs']])
    expect(toast.warning).not.toHaveBeenCalled()
    expect(toast.error).not.toHaveBeenCalled()
  })
  it('toasts when a run cannot start', async () => {
    startRun.execute.mockRejectedValue(new Error('A scrape is already running.'))
    mountApp()

    await useRunStore().start(['django'], ['upwork'], false)
    await vi.advanceTimersByTimeAsync(0)

    expect(toast.error).toHaveBeenCalledWith('A scrape is already running.')
  })

  it('toasts the same start error again on a second try', async () => {
    startRun.execute.mockRejectedValue(new Error('A scrape is already running.'))
    mountApp()
    const store = useRunStore()

    await store.start(['django'], ['upwork'], false)
    await vi.advanceTimersByTimeAsync(0)
    await store.start(['django'], ['upwork'], false)
    await vi.advanceTimersByTimeAsync(0)

    expect(toast.error).toHaveBeenCalledTimes(2)
  })

  it('toasts when the run is lost after repeated failed polls', async () => {
    startRun.execute.mockResolvedValue({ ...RUN, status: 'running' })
    getRun.execute.mockRejectedValue(new Error('timeout'))
    mountApp()

    await useRunStore().start(['django'], ['upwork'], false)
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * MAX_POLL_FAILURES)

    expect(toast.error).toHaveBeenCalledWith('Lost track of this run. Reload the page to check it.')
  })
})

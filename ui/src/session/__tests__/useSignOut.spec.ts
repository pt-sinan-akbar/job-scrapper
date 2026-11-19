import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { provideAuthUseCases } from '@/modules/auth/presentation/stores/authUseCases'
import type { RunRecord } from '@/modules/runs/domain/entities/Run'
import { provideRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'
import { POLL_INTERVAL_MS, useRunStore } from '@/modules/runs/presentation/stores/useRunStore'
import { useSignOut } from '@/session/useSignOut'

const getSession = { execute: vi.fn() }
const login = { execute: vi.fn() }
const logout = { execute: vi.fn() }
const getOptions = { execute: vi.fn() }
const getRun = { execute: vi.fn() }
const getLatestRun = { execute: vi.fn() }
const startRun = { execute: vi.fn() }

const RUNNING: RunRecord = {
  id: 'run-1',
  status: 'running',
  keywords: ['django'],
  sites: ['upwork'],
  startedAt: '2026-11-01T10:00:00+00:00',
  finishedAt: null,
  jobCount: 0,
  errorCount: 0,
  error: null,
  discordStatus: null,
  discordSent: 0,
  discordFailed: 0,
  discordError: null,
}

function createTestRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/login', component: { template: '<div />' } },
    ],
  })
}

async function mountSignOut(router: Router): Promise<() => Promise<void>> {
  let signOut: () => Promise<void> = async () => undefined
  const Host = defineComponent({
    setup() {
      signOut = useSignOut()
      return () => null
    },
  })
  await router.push('/')
  mount(Host, { global: { plugins: [router] } })
  return signOut
}

describe('useSignOut', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    setActivePinia(createPinia())
    provideAuthUseCases({ getSession, login, logout })
    provideRunUseCases({ getOptions, getRun, getLatestRun, startRun })
    logout.execute.mockResolvedValue(undefined)
    startRun.execute.mockResolvedValue(RUNNING)
    getRun.execute.mockResolvedValue({ record: RUNNING, jobs: [], failures: [] })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('stops following the run and goes to the login page', async () => {
    const router = createTestRouter()
    const signOut = await mountSignOut(router)
    const runs = useRunStore()
    await runs.start(['django'], ['upwork'], false)

    await signOut()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

    expect(logout.execute).toHaveBeenCalledTimes(1)
    expect(getRun.execute).not.toHaveBeenCalled()
    expect(runs.isRunning).toBe(false)
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('clears the latest run shown in Results', async () => {
    getLatestRun.execute.mockResolvedValue({
      record: { ...RUNNING, status: 'succeeded' },
      jobs: [],
      failures: [],
    })
    const router = createTestRouter()
    const signOut = await mountSignOut(router)
    const runs = useRunStore()
    await runs.loadLatest()

    await signOut()
    await flushPromises()

    expect(runs.latestRun).toBeNull()
    expect(runs.latestStatus).toBe('idle')
  })

  it('keeps following the run when the sign out fails', async () => {
    logout.execute.mockRejectedValue(new Error('down'))
    const router = createTestRouter()
    const signOut = await mountSignOut(router)
    const runs = useRunStore()
    await runs.start(['django'], ['upwork'], false)

    await expect(signOut()).rejects.toThrow('down')

    expect(runs.isRunning).toBe(true)
    expect(router.currentRoute.value.path).toBe('/')
  })
})

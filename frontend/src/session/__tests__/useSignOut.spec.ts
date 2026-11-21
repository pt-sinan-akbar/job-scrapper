import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { provideAuthUseCases } from '@/modules/auth/presentation/stores/authUseCases'
import type { ScrapeRecord } from '@/modules/scrapes/domain/entities/Scrape'
import { provideScrapeUseCases } from '@/modules/scrapes/presentation/stores/scrapeUseCases'
import {
  POLL_INTERVAL_MS,
  useScrapeStore,
} from '@/modules/scrapes/presentation/stores/useScrapeStore'
import { useSignOut } from '@/session/useSignOut'

const getSession = { execute: vi.fn() }
const login = { execute: vi.fn() }
const logout = { execute: vi.fn() }
const getOptions = { execute: vi.fn() }
const getScrape = { execute: vi.fn() }
const getLatestScrape = { execute: vi.fn() }
const startScrape = { execute: vi.fn() }
const sendLatestScrapeToDiscord = { execute: vi.fn() }

const RUNNING: ScrapeRecord = {
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
    provideScrapeUseCases({
      getOptions,
      getScrape,
      getLatestScrape,
      startScrape,
      sendLatestScrapeToDiscord,
    })
    logout.execute.mockResolvedValue(undefined)
    startScrape.execute.mockResolvedValue(RUNNING)
    getScrape.execute.mockResolvedValue({ record: RUNNING, jobs: [], failures: [] })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('stops following the scrape and goes to the login page', async () => {
    const router = createTestRouter()
    const signOut = await mountSignOut(router)
    const scrapes = useScrapeStore()
    await scrapes.start(['django'], ['upwork'], false)

    await signOut()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

    expect(logout.execute).toHaveBeenCalledTimes(1)
    expect(getScrape.execute).not.toHaveBeenCalled()
    expect(scrapes.isScraping).toBe(false)
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('clears the latest scrape shown in Results', async () => {
    getLatestScrape.execute.mockResolvedValue({
      record: { ...RUNNING, status: 'succeeded' },
      jobs: [],
      failures: [],
    })
    const router = createTestRouter()
    const signOut = await mountSignOut(router)
    const scrapes = useScrapeStore()
    await scrapes.loadLatest()

    await signOut()
    await flushPromises()

    expect(scrapes.latestScrape).toBeNull()
    expect(scrapes.latestStatus).toBe('idle')
  })

  it('keeps following the scrape when the sign out fails', async () => {
    logout.execute.mockRejectedValue(new Error('down'))
    const router = createTestRouter()
    const signOut = await mountSignOut(router)
    const scrapes = useScrapeStore()
    await scrapes.start(['django'], ['upwork'], false)

    await expect(signOut()).rejects.toThrow('down')

    expect(scrapes.isScraping).toBe(true)
    expect(router.currentRoute.value.path).toBe('/')
  })
})

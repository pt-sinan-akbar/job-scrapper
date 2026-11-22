import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import { createMemoryStorage } from '@/__tests__/memoryStorage'
import type { ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import type { DiscordSettings } from '@/modules/discord/domain/entities/Discord'
import { provideDiscordUseCases } from '@/modules/discord/presentation/stores/discordUseCases'
import type {
  ScrapeDetail,
  ScrapeJob,
  ScrapeOptions,
  ScrapeRecord,
} from '@/modules/scrapes/domain/entities/Scrape'
import ScrapesPage from '@/modules/scrapes/presentation/pages/ScrapesPage.vue'
import { provideScrapeUseCases } from '@/modules/scrapes/presentation/stores/scrapeUseCases'
import {
  MAX_POLL_FAILURES,
  POLL_INTERVAL_MS,
  useScrapeStore,
} from '@/modules/scrapes/presentation/stores/useScrapeStore'

const getSettings = { execute: vi.fn() }
const getOptions = { execute: vi.fn() }
const getScrape = { execute: vi.fn() }
const getLatestScrape = { execute: vi.fn() }
const startScrape = { execute: vi.fn() }
const sendLatestScrapeToDiscord = { execute: vi.fn() }

const OPTIONS: ScrapeOptions = {
  sites: [{ name: 'upwork', isEnabled: true }],
  isStale: false,
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

function detailOf(record: ScrapeRecord, overrides: Partial<ScrapeDetail> = {}): ScrapeDetail {
  return { record, jobs: [], failures: [], ...overrides }
}

function jobOf(overrides: Partial<ScrapeJob>): ScrapeJob {
  return {
    site: null,
    matchedKeyword: null,
    title: null,
    company: null,
    location: null,
    url: null,
    postedAt: null,
    salary: null,
    workType: null,
    employmentType: null,
    experienceLevel: null,
    description: null,
    json: {},
    ...overrides,
  }
}

const LATEST: ScrapeDetail = detailOf(
  { ...SCRAPE, id: 'run-0', keywords: ['vue'], sites: ['indeed'] },
  {
    jobs: [
      jobOf({
        site: 'indeed',
        matchedKeyword: 'vue',
        title: 'Vue dev',
        company: 'Acme',
        location: 'Remote',
        url: 'https://example.com/vue',
        json: { site: 'indeed', matched_keyword: 'vue', title: 'Vue dev' },
      }),
    ],
  },
)

const FINISHED: ScrapeDetail = detailOf(SCRAPE, {
  jobs: [
    jobOf({
      site: 'upwork',
      matchedKeyword: 'django',
      title: 'Django dev',
      company: 'Beta',
      url: 'https://example.com/django',
      json: { site: 'upwork', matched_keyword: 'django', title: 'Django dev' },
    }),
  ],
})

const SETTINGS: DiscordSettings = {
  isConfigured: true,
  tokenHint: '••••1234',
  defaultChannelId: '12345678901234567',
  mentionUserId: null,
  messageTemplate: '{title}',
  maxChars: 1900,
  updatedAt: null,
}

const CONFIG_SNAPSHOT: ConfigSnapshot = {
  values: {
    fields: ['title'],
    sites: [],
  },
  version: 4,
  updatedAt: '2026-11-02T01:00:00+00:00',
  updatedBy: 'ui',
  isStale: false,
  jobFields: ['site', 'title', 'company'],
  mandatoryFields: ['site', 'company'],
  locationOptions: [],
}

const PAGE_STUBS = {
  RouterLink: RouterLinkStub,
  ScrapeConfigSection: { template: '<section><h3>Config</h3></section>' },
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve: (value: T) => void = () => undefined
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

async function mountPage(path = '/scrapes') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/scrapes', component: ScrapesPage }],
  })
  await router.push(path)
  await router.isReady()
  return mount(ScrapesPage, {
    global: { plugins: [router, pinia], stubs: PAGE_STUBS },
    attachTo: document.body,
  })
}

type Wrapper = Awaited<ReturnType<typeof mountPage>>

function keywordInput(wrapper: Wrapper): HTMLInputElement {
  return wrapper.get('#scrape-keywords').element as HTMLInputElement
}

async function startWith(wrapper: Wrapper): Promise<void> {
  await wrapper.get('#scrape-keywords').setValue('django')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

describe('ScrapesPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    provideScrapeUseCases({
      getOptions,
      getScrape,
      getLatestScrape,
      startScrape,
      sendLatestScrapeToDiscord,
    })
    provideDiscordUseCases({
      getSettings,
      saveSettings: { execute: vi.fn() },
      testConnection: { execute: vi.fn() },
      listChannels: { execute: vi.fn() },
      previewMessage: { execute: vi.fn() },
      sendMessage: { execute: vi.fn() },
    })
    getSettings.execute.mockResolvedValue(SETTINGS)
    getLatestScrape.execute.mockResolvedValue(null)
    vi.stubGlobal('localStorage', createMemoryStorage())
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('shows a skeleton for the form until the first load finishes', async () => {
    const options = deferred<ScrapeOptions>()
    getOptions.execute.mockReturnValue(options.promise)
    const wrapper = await mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('Loading run options')
    expect(wrapper.find('#scrape-keywords').exists()).toBe(false)

    options.resolve(OPTIONS)
    await flushPromises()

    expect(wrapper.text()).not.toContain('Loading run options')
    expect(keywordInput(wrapper).value).toBe('')
  })

  it('keeps typed keywords on screen while it loads again', async () => {
    getOptions.execute.mockResolvedValueOnce(OPTIONS)
    const wrapper = await mountPage()
    await flushPromises()
    await wrapper.get('#scrape-keywords').setValue('django, vue')

    getOptions.execute.mockReturnValueOnce(deferred<ScrapeOptions>().promise)
    void useScrapeStore().load()
    await flushPromises()

    expect(wrapper.text()).not.toContain('Loading run options')
    expect(keywordInput(wrapper).value).toBe('django, vue')
  })

  it('shows a load error inside the start card', async () => {
    getOptions.execute.mockRejectedValue(new Error('Scraper down'))
    const wrapper = await mountPage()
    await flushPromises()

    const alert = wrapper.get('[role="alert"]')
    expect(alert.text()).toContain('Could not load runs')
    expect(alert.text()).toContain('Scraper down')
  })

  it('loads again when Try again is pressed after an error', async () => {
    getOptions.execute.mockRejectedValueOnce(new Error('Scraper down')).mockResolvedValue(OPTIONS)
    const wrapper = await mountPage()
    await flushPromises()

    const retry = wrapper.findAll('button').find((button) => button.text() === 'Try again')!
    await retry.trigger('click')
    await flushPromises()

    expect(getOptions.execute).toHaveBeenCalledTimes(2)
    expect(keywordInput(wrapper).value).toBe('')
  })

  it('hides Results when there has been no scrape yet', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    const wrapper = await mountPage()
    await flushPromises()

    const headings = wrapper.findAll('section h3').map((heading) => heading.text())

    expect(headings).toEqual(['Start a run', 'Config'])
    expect(wrapper.find('[role="log"]').exists()).toBe(false)
  })

  it('shows Results for the latest scrape between Start a scrape and Config', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    getLatestScrape.execute.mockResolvedValue(LATEST)
    const wrapper = await mountPage()
    await flushPromises()

    const headings = wrapper.findAll('section h3').map((heading) => heading.text())

    expect(headings).toEqual(['Start a run', 'Results', 'Config'])
    expect(getLatestScrape.execute).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('Vue dev')
  })

  it('shows a skeleton in Results while the latest scrape loads', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    const latest = deferred<ScrapeDetail | null>()
    getLatestScrape.execute.mockReturnValue(latest.promise)
    const wrapper = await mountPage()
    await flushPromises()

    const skeleton = wrapper.get('[data-slot="results-skeleton"]')
    expect(skeleton.attributes('role')).toBe('status')
    expect(skeleton.attributes('aria-busy')).toBe('true')
    expect(skeleton.findAll('[data-slot="skeleton"]').length).toBeGreaterThan(0)

    latest.resolve(LATEST)
    await flushPromises()

    expect(wrapper.find('[data-slot="results-skeleton"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Vue dev')
  })

  it('drops Results once the latest load finds no scrape', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    const latest = deferred<ScrapeDetail | null>()
    getLatestScrape.execute.mockReturnValue(latest.promise)
    const wrapper = await mountPage()
    await flushPromises()

    latest.resolve(null)
    await flushPromises()

    expect(wrapper.findAll('section h3').map((heading) => heading.text())).toEqual([
      'Start a run',
      'Config',
    ])
  })

  it('says so in Results when the latest scrape cannot be loaded and retries', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    getLatestScrape.execute
      .mockRejectedValueOnce(new Error('Scraper down'))
      .mockResolvedValue(LATEST)
    const wrapper = await mountPage()
    await flushPromises()

    const alert = wrapper.get('[data-slot="results-error"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('Scraper down')

    await alert.get('button').trigger('click')
    await flushPromises()

    expect(getLatestScrape.execute).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('Vue dev')
  })

  it('gives the config card the config anchor', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    getLatestScrape.execute.mockResolvedValue(LATEST)
    const wrapper = await mountPage()
    await flushPromises()

    const sections = wrapper.findAll('section')

    expect(sections[sections.length - 1]!.attributes('id')).toBe('config')
  })

  it('blocks Run scrape while the config has unsaved changes', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    const wrapper = await mountPage()
    await flushPromises()
    await wrapper.get('#scrape-keywords').setValue('django')

    const config = useConfigStore()
    config.snapshot = CONFIG_SNAPSHOT
    config.values = { ...structuredClone(CONFIG_SNAPSHOT.values), fields: ['url'] }
    await nextTick()

    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Save or discard config changes first')

    config.discard()
    await nextTick()

    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })

  describe('a running scrape', () => {
    beforeEach(() => {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
      getOptions.execute.mockResolvedValue(OPTIONS)
      startScrape.execute.mockResolvedValue({ ...SCRAPE, status: 'running' })
    })

    it('locks the start button while the scrape is active', async () => {
      getScrape.execute
        .mockResolvedValueOnce(detailOf({ ...SCRAPE, status: 'running' }))
        .mockResolvedValue(detailOf(SCRAPE))
      const wrapper = await mountPage()
      await flushPromises()

      await startWith(wrapper)

      const submit = wrapper.get('button[type="submit"]')
      expect(submit.text()).toContain('Scrape running')
      expect(submit.attributes('disabled')).toBeDefined()

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2)

      expect(wrapper.get('button[type="submit"]').text()).toContain('Run scrape')
    })

    it('shows a skeleton in Results while the scrape is processing', async () => {
      getLatestScrape.execute.mockResolvedValue(LATEST)
      getScrape.execute.mockResolvedValue(detailOf({ ...SCRAPE, status: 'running' }))
      const wrapper = await mountPage()
      await flushPromises()

      await startWith(wrapper)
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(wrapper.find('[data-slot="results-skeleton"]').exists()).toBe(true)
      expect(wrapper.text()).toContain('Loading results')
      expect(wrapper.text()).not.toContain('Vue dev')
    })

    it('covers the screen with the scrape progress until Keep browsing is clicked', async () => {
      getScrape.execute.mockResolvedValue(detailOf({ ...SCRAPE, status: 'running' }))
      const wrapper = await mountPage()
      await flushPromises()

      await startWith(wrapper)
      const overlaySelector = '[data-slot="scrape-progress-overlay"]'
      expect(document.body.querySelector(overlaySelector)).not.toBeNull()

      document.body.querySelector<HTMLButtonElement>('[data-slot="scrape-overlay-hide"]')!.click()
      await flushPromises()
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(document.body.querySelector(overlaySelector)).toBeNull()
      expect(wrapper.find('[data-slot="scrape-progress"]').exists()).toBe(true)
    })

    it('closes the full screen progress once the scrape ends', async () => {
      getScrape.execute
        .mockResolvedValueOnce(detailOf({ ...SCRAPE, status: 'running' }))
        .mockResolvedValue(FINISHED)
      const wrapper = await mountPage()
      await flushPromises()
      await startWith(wrapper)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2)
      await flushPromises()

      expect(document.body.querySelector('[data-slot="scrape-progress-overlay"]')).toBeNull()
      expect(wrapper.text()).toContain('Django dev')
    })

    it('shows the detail of the scrape once it ends', async () => {
      getScrape.execute
        .mockResolvedValueOnce(detailOf({ ...SCRAPE, status: 'running' }))
        .mockResolvedValue(FINISHED)
      const wrapper = await mountPage()
      await flushPromises()
      await startWith(wrapper)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2)

      expect(wrapper.find('[data-slot="results-skeleton"]').exists()).toBe(false)
      expect(wrapper.text()).toContain('Django dev')
      expect(wrapper.findAll('section h3').map((heading) => heading.text())).toEqual([
        'Start a run',
        'Results',
        'Config',
      ])
    })

    it('shows no history or live log block for the scrape', async () => {
      getScrape.execute.mockResolvedValue(detailOf(SCRAPE))
      const wrapper = await mountPage()
      await flushPromises()
      await startWith(wrapper)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(wrapper.text()).not.toContain('History')
      expect(wrapper.find('[role="log"]').exists()).toBe(false)
    })

    it('keeps polling after the user leaves the Runs page', async () => {
      getScrape.execute
        .mockResolvedValueOnce(detailOf({ ...SCRAPE, status: 'running' }))
        .mockResolvedValueOnce(detailOf({ ...SCRAPE, status: 'running' }))
        .mockResolvedValueOnce(detailOf(SCRAPE))
      const wrapper = await mountPage()
      await flushPromises()
      await startWith(wrapper)
      const store = useScrapeStore()

      wrapper.unmount()
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(getScrape.execute).toHaveBeenCalledTimes(3)
      expect(store.isScraping).toBe(false)
      expect(store.scrapeOutcome?.status).toBe('succeeded')
    })

    it('follows a scrape that is still going after a reload until it ends', async () => {
      getLatestScrape.execute.mockResolvedValue(detailOf({ ...SCRAPE, status: 'running' }))
      getScrape.execute
        .mockResolvedValueOnce(detailOf({ ...SCRAPE, status: 'running' }))
        .mockResolvedValue(FINISHED)
      const wrapper = await mountPage()
      await flushPromises()

      expect(wrapper.find('[data-slot="results-skeleton"]').exists()).toBe(true)
      expect(wrapper.get('button[type="submit"]').text()).toContain('Scrape running')
      expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2)

      expect(getScrape.execute).toHaveBeenCalledWith('run-1')
      expect(wrapper.find('[data-slot="results-skeleton"]').exists()).toBe(false)
      expect(wrapper.text()).toContain('Django dev')
      expect(wrapper.get('button[type="submit"]').text()).toContain('Run scrape')
      expect(useScrapeStore().scrapeOutcome?.status).toBe('succeeded')
    })

    it('says the scrape was lost instead of showing the older results', async () => {
      getLatestScrape.execute.mockResolvedValue(LATEST)
      getScrape.execute.mockRejectedValue(new Error('timeout'))
      const wrapper = await mountPage()
      await flushPromises()
      await startWith(wrapper)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * MAX_POLL_FAILURES)

      expect(wrapper.get('[data-slot="results-lost"]').text()).toContain('Lost track of this run')
      expect(wrapper.text()).not.toContain('Vue dev')
    })

    it('does not start a second poll loop when the page mounts again', async () => {
      getScrape.execute.mockResolvedValue(detailOf({ ...SCRAPE, status: 'running' }))
      const wrapper = await mountPage()
      await flushPromises()
      await startWith(wrapper)
      const pinia = wrapper.vm.$pinia
      wrapper.unmount()

      const again = mount(ScrapesPage, {
        global: { plugins: [pinia, wrapper.vm.$router], stubs: PAGE_STUBS },
        attachTo: document.body,
      })
      await flushPromises()
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(getScrape.execute).toHaveBeenCalledTimes(3)
      expect(again.get('button[type="submit"]').text()).toContain('Scrape running')
    })
  })

  describe('the config link', () => {
    const scrollIntoView = vi.fn<Element['scrollIntoView']>()

    function stubReducedMotion(isReduced: boolean): void {
      vi.stubGlobal(
        'matchMedia',
        vi.fn().mockImplementation((query: string) => ({
          matches: isReduced,
          media: query,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        })),
      )
    }

    beforeEach(() => {
      scrollIntoView.mockReset()
      Element.prototype.scrollIntoView = scrollIntoView
      getOptions.execute.mockResolvedValue(OPTIONS)
      stubReducedMotion(false)
    })

    it('scrolls smoothly to the config card once the loads settle', async () => {
      await mountPage('/scrapes#config')
      await flushPromises()
      expect(scrollIntoView).not.toHaveBeenCalled()

      useConfigStore().status = 'ready'
      await flushPromises()

      expect(scrollIntoView).toHaveBeenCalledTimes(1)
      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth' })
      expect(scrollIntoView.mock.contexts[0]).toBe(document.getElementById('config'))
    })

    it('jumps without motion when the user prefers reduced motion', async () => {
      stubReducedMotion(true)
      await mountPage('/scrapes#config')
      await flushPromises()

      useConfigStore().status = 'ready'
      await flushPromises()

      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'auto' })
    })

    it('scrolls only once even when the stores load again', async () => {
      await mountPage('/scrapes#config')
      await flushPromises()
      useConfigStore().status = 'ready'
      await flushPromises()

      useConfigStore().status = 'loading'
      await flushPromises()
      useConfigStore().status = 'ready'
      await flushPromises()

      expect(scrollIntoView).toHaveBeenCalledTimes(1)
    })

    it('drops the pending scroll when the page unmounts first', async () => {
      const wrapper = await mountPage('/scrapes#config')
      await flushPromises()

      wrapper.unmount()
      useConfigStore().status = 'ready'
      await flushPromises()

      expect(scrollIntoView).not.toHaveBeenCalled()
    })

    it.each([['wheel'], ['touchstart'], ['keydown']])(
      'drops the pending scroll when the user scrolls first with %s',
      async (type) => {
        await mountPage('/scrapes#config')
        await flushPromises()

        window.dispatchEvent(new Event(type))
        useConfigStore().status = 'ready'
        await flushPromises()

        expect(scrollIntoView).not.toHaveBeenCalled()
      },
    )

    it('does not scroll without the config hash', async () => {
      await mountPage('/scrapes')
      useConfigStore().status = 'ready'
      await flushPromises()

      expect(scrollIntoView).not.toHaveBeenCalled()
    })
  })

  describe('discord send', () => {
    function notifyBox(wrapper: Wrapper) {
      return wrapper.get('#scrape-notify-discord')
    }

    it('enables the toggle when a default channel is set', async () => {
      getOptions.execute.mockResolvedValue(OPTIONS)
      const wrapper = await mountPage()
      await flushPromises()

      expect(getSettings.execute).toHaveBeenCalledTimes(1)
      expect(notifyBox(wrapper).attributes('disabled')).toBeUndefined()
    })

    it.each<[string, DiscordSettings, string]>([
      [
        'no default channel',
        { ...SETTINGS, defaultChannelId: null },
        'Set a default channel on the Discord page',
      ],
      [
        'no bot token',
        { ...SETTINGS, isConfigured: false },
        'Save a bot token on the Discord page',
      ],
    ])('disables the toggle with %s and says what to do', async (_label, settings, hint) => {
      getSettings.execute.mockResolvedValue(settings)
      getOptions.execute.mockResolvedValue(OPTIONS)
      const wrapper = await mountPage()
      await flushPromises()

      expect(notifyBox(wrapper).attributes('disabled')).toBeDefined()
      expect(wrapper.text()).toContain(hint)
    })

    it('disables the toggle without a hint while the settings load', async () => {
      getSettings.execute.mockReturnValue(deferred<DiscordSettings>().promise)
      getOptions.execute.mockResolvedValue(OPTIONS)
      const wrapper = await mountPage()
      await flushPromises()

      expect(notifyBox(wrapper).attributes('disabled')).toBeDefined()
      expect(wrapper.find('[data-slot="discord-hint"]').exists()).toBe(false)
    })

    it('disables the toggle and says so when the settings cannot be loaded', async () => {
      getSettings.execute.mockRejectedValue(new Error('down'))
      getOptions.execute.mockResolvedValue(OPTIONS)
      const wrapper = await mountPage()
      await flushPromises()

      expect(notifyBox(wrapper).attributes('disabled')).toBeDefined()
      expect(wrapper.text()).toContain('Could not load Discord settings')
    })

    it('starts the scrape with the toggle choice', async () => {
      getOptions.execute.mockResolvedValue(OPTIONS)
      startScrape.execute.mockResolvedValue({ ...SCRAPE, status: 'running' })
      const wrapper = await mountPage()
      await flushPromises()
      await notifyBox(wrapper).trigger('click')

      await startWith(wrapper)

      expect(startScrape.execute).toHaveBeenCalledWith(['django'], ['upwork'], true)
    })

    it('starts the scrape without a send when the toggle is off', async () => {
      getOptions.execute.mockResolvedValue(OPTIONS)
      startScrape.execute.mockResolvedValue({ ...SCRAPE, status: 'running' })
      const wrapper = await mountPage()
      await flushPromises()

      await startWith(wrapper)

      expect(startScrape.execute).toHaveBeenCalledWith(['django'], ['upwork'], false)
    })
  })
})

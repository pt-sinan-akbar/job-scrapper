import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import { createMemoryStorage } from '@/__tests__/memoryStorage'
import { EMPTY_FILTER, type ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import type { DiscordSettings } from '@/modules/discord/domain/entities/Discord'
import { provideDiscordUseCases } from '@/modules/discord/presentation/stores/discordUseCases'
import type { RunOptions, RunRecord } from '@/modules/runs/domain/entities/Run'
import RunsPage from '@/modules/runs/presentation/pages/RunsPage.vue'
import { provideRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'
import { POLL_INTERVAL_MS, useRunStore } from '@/modules/runs/presentation/stores/useRunStore'

const getSettings = { execute: vi.fn() }
const getOptions = { execute: vi.fn() }
const getRun = { execute: vi.fn() }
const startRun = { execute: vi.fn() }

const OPTIONS: RunOptions = {
  keywords: ['django'],
  sites: [{ name: 'upwork', isEnabled: true }],
  isStale: false,
}

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
    keywords: ['django'],
    limit: 3,
    concurrency: 2,
    maxAgeHours: 72,
    filter: EMPTY_FILTER,
    defaultFields: ['title'],
    sites: [],
  },
  version: 4,
  updatedAt: '2026-11-02T01:00:00+00:00',
  updatedBy: 'ui',
  isStale: false,
  jobFields: ['site', 'title', 'company'],
  mandatoryFields: ['site', 'company'],
  locationOptions: {},
}

const PAGE_STUBS = {
  RouterLink: RouterLinkStub,
  RunConfigSection: { template: '<section><h3>Config</h3></section>' },
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve: (value: T) => void = () => undefined
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

async function mountPage(path = '/runs') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/runs', component: RunsPage }],
  })
  await router.push(path)
  await router.isReady()
  return mount(RunsPage, {
    global: { plugins: [router, pinia], stubs: PAGE_STUBS },
    attachTo: document.body,
  })
}

type Wrapper = Awaited<ReturnType<typeof mountPage>>

function keywordInput(wrapper: Wrapper): HTMLInputElement {
  return wrapper.get('#run-keywords').element as HTMLInputElement
}

async function startWith(wrapper: Wrapper): Promise<void> {
  await wrapper.get('#run-keywords').setValue('django')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

describe('RunsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    provideRunUseCases({ getOptions, getRun, startRun })
    provideDiscordUseCases({
      getSettings,
      saveSettings: { execute: vi.fn() },
      testConnection: { execute: vi.fn() },
      listChannels: { execute: vi.fn() },
      previewMessage: { execute: vi.fn() },
      sendMessage: { execute: vi.fn() },
    })
    getSettings.execute.mockResolvedValue(SETTINGS)
    vi.stubGlobal('localStorage', createMemoryStorage())
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('shows a skeleton for the form until the first load finishes', async () => {
    const options = deferred<RunOptions>()
    getOptions.execute.mockReturnValue(options.promise)
    const wrapper = await mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('Loading run options')
    expect(wrapper.find('#run-keywords').exists()).toBe(false)

    options.resolve(OPTIONS)
    await flushPromises()

    expect(wrapper.text()).not.toContain('Loading run options')
    expect(keywordInput(wrapper).value).toBe('')
  })

  it('keeps typed keywords on screen while it loads again', async () => {
    getOptions.execute.mockResolvedValueOnce(OPTIONS)
    const wrapper = await mountPage()
    await flushPromises()
    await wrapper.get('#run-keywords').setValue('django, vue')

    getOptions.execute.mockReturnValueOnce(deferred<RunOptions>().promise)
    void useRunStore().load()
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

  it('shows only Start a run with Config right below it', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    const wrapper = await mountPage()
    await flushPromises()

    const headings = wrapper.findAll('section h3').map((heading) => heading.text())

    expect(headings).toEqual(['Start a run', 'Config'])
    expect(wrapper.find('[role="log"]').exists()).toBe(false)
  })

  it('gives the config card the config anchor', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    const wrapper = await mountPage()
    await flushPromises()

    expect(wrapper.findAll('section')[1]!.attributes('id')).toBe('config')
  })

  it('blocks Run scrape while the config has unsaved changes', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    const wrapper = await mountPage()
    await flushPromises()
    await wrapper.get('#run-keywords').setValue('django')

    const config = useConfigStore()
    config.snapshot = CONFIG_SNAPSHOT
    config.values = { ...structuredClone(CONFIG_SNAPSHOT.values), limit: 9 }
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
      startRun.execute.mockResolvedValue({ ...RUN, status: 'running' })
    })

    it('locks the start button while the run is active', async () => {
      getRun.execute.mockResolvedValueOnce({ ...RUN, status: 'running' }).mockResolvedValue(RUN)
      const wrapper = await mountPage()
      await flushPromises()

      await startWith(wrapper)

      const submit = wrapper.get('button[type="submit"]')
      expect(submit.text()).toContain('Scrape running')
      expect(submit.attributes('disabled')).toBeDefined()

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2)

      expect(wrapper.get('button[type="submit"]').text()).toContain('Run scrape')
    })

    it('shows no inline status block for the run', async () => {
      getRun.execute.mockResolvedValue(RUN)
      const wrapper = await mountPage()
      await flushPromises()
      await startWith(wrapper)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(wrapper.text()).not.toContain('Results')
      expect(wrapper.text()).not.toContain('History')
      expect(wrapper.text()).not.toContain('4 jobs')
    })

    it('keeps polling after the user leaves the Runs page', async () => {
      getRun.execute
        .mockResolvedValueOnce({ ...RUN, status: 'running' })
        .mockResolvedValueOnce({ ...RUN, status: 'running' })
        .mockResolvedValueOnce(RUN)
      const wrapper = await mountPage()
      await flushPromises()
      await startWith(wrapper)
      const store = useRunStore()

      wrapper.unmount()
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(getRun.execute).toHaveBeenCalledTimes(3)
      expect(store.isRunning).toBe(false)
      expect(store.runOutcome?.status).toBe('succeeded')
    })

    it('does not start a second poll loop when the page mounts again', async () => {
      getRun.execute.mockResolvedValue({ ...RUN, status: 'running' })
      const wrapper = await mountPage()
      await flushPromises()
      await startWith(wrapper)
      const pinia = wrapper.vm.$pinia
      wrapper.unmount()

      const again = mount(RunsPage, {
        global: { plugins: [pinia, wrapper.vm.$router], stubs: PAGE_STUBS },
        attachTo: document.body,
      })
      await flushPromises()
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(getRun.execute).toHaveBeenCalledTimes(3)
      expect(again.get('button[type="submit"]').text()).toContain('Scrape running')
    })
  })

  describe('the config link', () => {
    const scrollIntoView = vi.fn<Element['scrollIntoView']>()

    function stubReducedMotion(isReduced: boolean): void {
      vi.stubGlobal(
        'matchMedia',
        vi.fn().mockImplementation((query: string) => ({ matches: isReduced, media: query })),
      )
    }

    beforeEach(() => {
      scrollIntoView.mockReset()
      Element.prototype.scrollIntoView = scrollIntoView
      getOptions.execute.mockResolvedValue(OPTIONS)
      stubReducedMotion(false)
    })

    it('scrolls smoothly to the config card once the loads settle', async () => {
      await mountPage('/runs#config')
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
      await mountPage('/runs#config')
      await flushPromises()

      useConfigStore().status = 'ready'
      await flushPromises()

      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'auto' })
    })

    it('scrolls only once even when the stores load again', async () => {
      await mountPage('/runs#config')
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
      const wrapper = await mountPage('/runs#config')
      await flushPromises()

      wrapper.unmount()
      useConfigStore().status = 'ready'
      await flushPromises()

      expect(scrollIntoView).not.toHaveBeenCalled()
    })

    it.each([['wheel'], ['touchstart'], ['keydown']])(
      'drops the pending scroll when the user scrolls first with %s',
      async (type) => {
        await mountPage('/runs#config')
        await flushPromises()

        window.dispatchEvent(new Event(type))
        useConfigStore().status = 'ready'
        await flushPromises()

        expect(scrollIntoView).not.toHaveBeenCalled()
      },
    )

    it('does not scroll without the config hash', async () => {
      await mountPage('/runs')
      useConfigStore().status = 'ready'
      await flushPromises()

      expect(scrollIntoView).not.toHaveBeenCalled()
    })
  })

  describe('discord send', () => {
    function notifyBox(wrapper: Wrapper) {
      return wrapper.get('#run-notify-discord')
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

    it('starts the run with the toggle choice', async () => {
      getOptions.execute.mockResolvedValue(OPTIONS)
      startRun.execute.mockResolvedValue({ ...RUN, status: 'running' })
      const wrapper = await mountPage()
      await flushPromises()
      await notifyBox(wrapper).trigger('click')

      await startWith(wrapper)

      expect(startRun.execute).toHaveBeenCalledWith(['django'], ['upwork'], true)
    })

    it('starts the run without a send when the toggle is off', async () => {
      getOptions.execute.mockResolvedValue(OPTIONS)
      startRun.execute.mockResolvedValue({ ...RUN, status: 'running' })
      const wrapper = await mountPage()
      await flushPromises()

      await startWith(wrapper)

      expect(startRun.execute).toHaveBeenCalledWith(['django'], ['upwork'], false)
    })
  })
})

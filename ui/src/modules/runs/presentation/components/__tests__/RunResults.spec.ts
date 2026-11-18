import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createMemoryStorage } from '@/__tests__/memoryStorage'
import type { RunDetail } from '@/modules/runs/domain/entities/Run'
import RunResults from '@/modules/runs/presentation/components/RunResults.vue'
import { RESULTS_TAB_STORAGE_KEY } from '@/modules/runs/presentation/components/resultsTabStorage'

function makeDetail(overrides: Partial<RunDetail> = {}): RunDetail {
  return {
    record: {
      id: 'run-1',
      status: 'succeeded',
      keywords: ['AI Engineering', 'Vue'],
      sites: ['jobstreet', 'indeed'],
      startedAt: '2026-11-01T10:00:00+00:00',
      finishedAt: '2026-11-01T10:01:00+00:00',
      jobCount: 1,
      errorCount: 0,
      error: null,
      discordStatus: null,
      discordSent: 0,
      discordFailed: 0,
      discordError: null,
    },
    jobs: [
      {
        site: 'jobstreet',
        matchedKeyword: 'AI Engineering',
        title: 'ML Engineer',
        company: 'Acme',
        location: 'Remote',
        url: 'https://example.com/1',
        postedAt: null,
      },
    ],
    failures: [],
    payloads: [
      {
        keyword: 'AI Engineering',
        site: 'jobstreet',
        raw: { source: 'raw-jobstreet-ai' },
        filtered: { source: 'filtered-jobstreet-ai' },
      },
    ],
    ...overrides,
  }
}

interface Props {
  detail: RunDetail | null
  isPending: boolean
  isLost: boolean
  errorMessage: string | null
}

function mountResults(props: Partial<Props> = {}) {
  return mount(RunResults, {
    props: { detail: makeDetail(), isPending: false, isLost: false, errorMessage: null, ...props },
    attachTo: document.body,
  })
}

type Wrapper = ReturnType<typeof mountResults>

function tab(wrapper: Wrapper, name: string) {
  const found = wrapper.findAll('[role="tab"]').find((node) => node.text() === name)
  if (found === undefined) {
    throw new Error(`No tab named ${name}`)
  }
  return found
}

async function openTab(wrapper: Wrapper, name: string) {
  await tab(wrapper, name).trigger('mousedown', { button: 0, ctrlKey: false })
  await nextTick()
}

describe('RunResults', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createMemoryStorage())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('titles the card Results with the run keywords and sites', () => {
    const wrapper = mountResults()

    expect(wrapper.get('h3').text()).toBe('Results')
    expect(wrapper.text()).toContain('AI Engineering, Vue on jobstreet, indeed')
  })

  it('has a Jobs tab and a JSON tab and starts on Jobs', () => {
    const wrapper = mountResults()

    expect(wrapper.findAll('[role="tab"]').map((node) => node.text())).toEqual(['Jobs', 'JSON'])
    expect(tab(wrapper, 'Jobs').attributes('aria-selected')).toBe('true')
    expect(wrapper.text()).toContain('ML Engineer')
  })

  it('shows the payloads under JSON', async () => {
    const wrapper = mountResults()

    await openTab(wrapper, 'JSON')

    expect(wrapper.get('[data-slot="json-filtered"] pre').text()).toContain('filtered-jobstreet-ai')
    expect(wrapper.get('[data-slot="json-raw"] pre').text()).toContain('raw-jobstreet-ai')
  })

  it('remembers the last used tab', async () => {
    const first = mountResults()
    await openTab(first, 'JSON')

    expect(window.localStorage.getItem(RESULTS_TAB_STORAGE_KEY)).toBe('json')
    first.unmount()

    expect(tab(mountResults(), 'JSON').attributes('aria-selected')).toBe('true')
  })

  it('opens a tab when it gets keyboard focus', async () => {
    const wrapper = mountResults()

    ;(tab(wrapper, 'JSON').element as HTMLElement).focus()
    await flushPromises()

    expect(tab(wrapper, 'JSON').attributes('aria-selected')).toBe('true')
  })

  it('goes back to the first payload when another run is shown', async () => {
    const detail = makeDetail({
      payloads: [
        ...makeDetail().payloads,
        { keyword: 'Vue', site: 'indeed', raw: { source: 'raw-indeed-vue' }, filtered: null },
      ],
    })
    const wrapper = mountResults({ detail })
    await openTab(wrapper, 'JSON')
    await wrapper.findAll('[data-slot="payload-chip"]')[1]!.trigger('click')

    await wrapper.setProps({ detail: { ...detail, record: { ...detail.record, id: 'run-2' } } })

    expect(wrapper.get('[data-slot="json-raw"] pre').text()).toContain('raw-jobstreet-ai')
  })

  describe('while pending', () => {
    it('shows skeleton rows as a busy status instead of the tabs', () => {
      const wrapper = mountResults({ isPending: true })
      const skeleton = wrapper.get('[data-slot="results-skeleton"]')

      expect(skeleton.attributes('role')).toBe('status')
      expect(skeleton.attributes('aria-busy')).toBe('true')
      expect(skeleton.get('.sr-only').text()).toBe('Loading results')
      expect(skeleton.findAll('[data-slot="skeleton"]').length).toBeGreaterThan(2)
      expect(wrapper.find('[role="tab"]').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('ML Engineer')
    })

    it('hides the keywords of the older run it replaces', () => {
      const wrapper = mountResults({ isPending: true })

      expect(wrapper.text()).not.toContain('AI Engineering, Vue')
    })

    it('shows the skeleton when nothing has loaded yet', () => {
      const wrapper = mountResults({ isPending: true, detail: null })

      expect(wrapper.find('[data-slot="results-skeleton"]').exists()).toBe(true)
    })
  })

  describe('a lost run', () => {
    it('says the run was lost instead of showing the older results', () => {
      const wrapper = mountResults({ isLost: true })
      const lost = wrapper.get('[data-slot="results-lost"]')

      expect(lost.attributes('role')).toBe('status')
      expect(lost.text()).toContain('Lost track of this run. Reload to check it.')
      expect(wrapper.find('[role="tab"]').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('ML Engineer')
      expect(wrapper.text()).not.toContain('AI Engineering, Vue')
    })

    it('shows the lost note over the skeleton', () => {
      const wrapper = mountResults({ isLost: true, isPending: true })

      expect(wrapper.find('[data-slot="results-lost"]').exists()).toBe(true)
      expect(wrapper.find('[data-slot="results-skeleton"]').exists()).toBe(false)
    })
  })

  describe('a failed load', () => {
    it('says so and asks to try again when there is nothing to show', async () => {
      const wrapper = mountResults({ detail: null, errorMessage: 'Scraper down' })
      const alert = wrapper.get('[data-slot="results-error"]')

      expect(alert.attributes('role')).toBe('alert')
      expect(alert.text()).toContain('Could not load the latest run')
      expect(alert.text()).toContain('Scraper down')

      await alert.get('button').trigger('click')

      expect(wrapper.emitted('retry')).toHaveLength(1)
    })

    it('keeps showing the run it has over the error', () => {
      const wrapper = mountResults({ errorMessage: 'Scraper down' })

      expect(wrapper.find('[data-slot="results-error"]').exists()).toBe(false)
      expect(wrapper.text()).toContain('ML Engineer')
    })
  })
})

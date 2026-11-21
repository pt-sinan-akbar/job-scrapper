import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { ScrapeDetail, ScrapeJob } from '@/modules/scrapes/domain/entities/Scrape'
import ScrapeResults from '@/modules/scrapes/presentation/components/ScrapeResults.vue'

function makeJob(overrides: Partial<ScrapeJob> = {}): ScrapeJob {
  return {
    site: 'jobstreet',
    matchedKeyword: 'AI Engineering',
    title: 'ML Engineer',
    company: 'Acme',
    location: 'Remote',
    url: 'https://example.com/1',
    postedAt: null,
    salary: null,
    workType: null,
    employmentType: null,
    experienceLevel: null,
    description: null,
    json: { title: 'ML Engineer', job_id: 'job-ml' },
    ...overrides,
  }
}

const SECOND_JOB = makeJob({
  title: 'Vue Developer',
  url: 'https://example.com/2',
  json: { title: 'Vue Developer', job_id: 'job-vue' },
})

function makeDetail(overrides: Partial<ScrapeDetail> = {}): ScrapeDetail {
  return {
    record: {
      id: 'run-1',
      status: 'succeeded',
      keywords: ['AI Engineering', 'Vue'],
      sites: ['jobstreet', 'indeed'],
      startedAt: '2026-11-01T10:00:00+00:00',
      finishedAt: '2026-11-01T10:01:00+00:00',
      jobCount: 2,
      errorCount: 0,
      error: null,
      discordStatus: null,
      discordSent: 0,
      discordFailed: 0,
      discordError: null,
    },
    jobs: [makeJob(), SECOND_JOB],
    failures: [],
    ...overrides,
  }
}

interface Props {
  detail: ScrapeDetail | null
  isPending: boolean
  runningRecord?: ScrapeDetail['record'] | null
  isLost: boolean
  errorMessage: string | null
}

function mountResults(props: Partial<Props> = {}) {
  return mount(ScrapeResults, {
    props: { detail: makeDetail(), isPending: false, isLost: false, errorMessage: null, ...props },
    attachTo: document.body,
  })
}

function stubScreen(isWide: boolean): void {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches: isWide,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )
}

function panelText(wrapper: ReturnType<typeof mountResults>): string {
  return wrapper.get('[data-slot="job-json-panel"] pre').text()
}

function dialog(): HTMLElement | null {
  return document.body.querySelector('[role="dialog"]')
}

describe('ScrapeResults', () => {
  beforeEach(() => {
    stubScreen(true)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('titles the card Results with no keyword and site summary', () => {
    const wrapper = mountResults()

    expect(wrapper.get('h3').text()).toBe('Results')
    expect(wrapper.text()).not.toContain('AI Engineering, Vue on jobstreet, indeed')
  })

  it('shows the total job count next to the title', () => {
    const wrapper = mountResults()

    expect(wrapper.get('[data-slot="results-count"]').text()).toBe('2 jobs')
  })

  it('says 1 job for a single result', () => {
    const wrapper = mountResults({ detail: makeDetail({ jobs: [makeJob()] }) })

    expect(wrapper.get('[data-slot="results-count"]').text()).toBe('1 job')
  })

  it('shows the jobs without tabs', () => {
    const wrapper = mountResults()

    expect(wrapper.find('[role="tab"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-slot="job-card"]')).toHaveLength(2)
  })

  it('shows the JSON of the first job next to the jobs to start', () => {
    const wrapper = mountResults()

    expect(
      wrapper.get('[data-slot="job-aside"]').find('[data-slot="job-json-panel"]').exists(),
    ).toBe(true)
    expect(panelText(wrapper)).toContain('job-ml')
    expect(wrapper.findAll('[data-slot="job-card"]')[0]!.attributes('data-selected')).toBe('true')
  })

  it('shows the JSON of the job whose card is clicked', async () => {
    const wrapper = mountResults()

    await wrapper.findAll('[data-slot="job-card"]')[1]!.trigger('click')

    expect(panelText(wrapper)).toContain('job-vue')
    expect(panelText(wrapper)).not.toContain('job-ml')
    expect(wrapper.findAll('[data-slot="job-card"]')[1]!.attributes('data-selected')).toBe('true')
    expect(dialog()).toBeNull()
  })

  it('goes back to the first job when another scrape is shown', async () => {
    const detail = makeDetail()
    const wrapper = mountResults({ detail })
    await wrapper.findAll('[data-slot="job-card"]')[1]!.trigger('click')

    await wrapper.setProps({ detail: { ...detail, record: { ...detail.record, id: 'run-2' } } })

    expect(panelText(wrapper)).toContain('job-ml')
  })

  it('falls back to the first job when the selected one is gone', async () => {
    const detail = makeDetail()
    const wrapper = mountResults({ detail })
    await wrapper.findAll('[data-slot="job-card"]')[1]!.trigger('click')

    await wrapper.setProps({ detail: { ...detail, jobs: [makeJob()] } })

    expect(panelText(wrapper)).toContain('job-ml')
  })

  it('opens the selected job JSON full screen from the panel', async () => {
    const wrapper = mountResults()

    await wrapper.get('[data-slot="job-json-panel"] [data-slot="json-fullscreen"]').trigger('click')
    await flushPromises()

    expect(dialog()?.textContent).toContain('job-ml')
  })

  it('selects the job without a dialog when its card is clicked on a wide screen', async () => {
    const wrapper = mountResults()

    await wrapper.findAll('[data-slot="job-card"]')[1]!.trigger('click')
    await flushPromises()

    expect(panelText(wrapper)).toContain('job-vue')
    expect(dialog()).toBeNull()
  })

  it('opens the job JSON full screen when its card is clicked on a narrow screen', async () => {
    stubScreen(false)
    const wrapper = mountResults()

    await wrapper.findAll('[data-slot="job-card"]')[1]!.trigger('click')
    await flushPromises()

    expect(dialog()?.textContent).toContain('job-vue')
  })

  it('shows no JSON panel and marks no job on a narrow screen', () => {
    stubScreen(false)
    const wrapper = mountResults()

    expect(wrapper.find('[data-slot="job-json-panel"]').exists()).toBe(false)
    expect(wrapper.find('[data-slot="job-card"][data-selected]').exists()).toBe(false)
  })

  it('closes the full screen JSON when another scrape is shown', async () => {
    const detail = makeDetail()
    const wrapper = mountResults({ detail })
    await wrapper.get('[data-slot="job-json-panel"] [data-slot="json-fullscreen"]').trigger('click')
    await flushPromises()

    await wrapper.setProps({ detail: { ...detail, record: { ...detail.record, id: 'run-2' } } })
    await flushPromises()

    expect(dialog()).toBeNull()
  })

  it('stays on the first job when a shorter list grows back', async () => {
    const detail = makeDetail()
    const wrapper = mountResults({ detail })
    await wrapper.findAll('[data-slot="job-card"]')[1]!.trigger('click')

    await wrapper.setProps({ detail: { ...detail, jobs: [makeJob()] } })
    await wrapper.setProps({ detail })

    expect(panelText(wrapper)).toContain('job-ml')
  })

  it('shows no JSON panel when the scrape found no jobs', () => {
    const wrapper = mountResults({ detail: makeDetail({ jobs: [] }) })

    expect(wrapper.find('[data-slot="job-json-panel"]').exists()).toBe(false)
    expect(wrapper.get('[data-slot="empty-state"]').text()).toContain('No jobs found')
  })

  describe('while pending', () => {
    it('shows skeleton rows as a busy status instead of the jobs', () => {
      const wrapper = mountResults({ isPending: true })
      const skeleton = wrapper.get('[data-slot="results-skeleton"]')

      expect(skeleton.attributes('role')).toBe('status')
      expect(skeleton.attributes('aria-busy')).toBe('true')
      expect(skeleton.get('.sr-only').text()).toBe('Loading results')
      expect(skeleton.findAll('[data-slot="skeleton"]').length).toBeGreaterThan(2)
      expect(wrapper.find('[data-slot="job-json-panel"]').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('ML Engineer')
    })

    it('hides the keywords of the older scrape it replaces', () => {
      const wrapper = mountResults({ isPending: true })

      expect(wrapper.text()).not.toContain('AI Engineering, Vue')
    })

    it('hides the job count while pending', () => {
      const wrapper = mountResults({ isPending: true })

      expect(wrapper.find('[data-slot="results-count"]').exists()).toBe(false)
    })

    it('shows the scrape progress with its keywords and sites while a scrape runs', () => {
      const runningRecord = {
        ...makeDetail().record,
        status: 'running' as const,
        keywords: ['Data analyst'],
        sites: ['glints', 'linkedin'],
      }
      const wrapper = mountResults({ isPending: true, runningRecord })
      const progress = wrapper.get('[data-slot="scrape-progress"]')

      expect(progress.get('[data-slot="scrape-progress-title"]').text()).toBe('Scraping 2 sites')
      expect(progress.get('[data-slot="scrape-progress-keywords"]').text()).toBe('Data analyst')
      expect(progress.findAll('li').map((item) => item.text())).toEqual(['glints', 'linkedin'])
    })

    it('shows only the skeleton when no scrape is running', () => {
      const wrapper = mountResults({ isPending: true, runningRecord: null })

      expect(wrapper.find('[data-slot="scrape-progress"]').exists()).toBe(false)
      expect(wrapper.find('[data-slot="results-skeleton"]').exists()).toBe(true)
    })

    it('shows the skeleton when nothing has loaded yet', () => {
      const wrapper = mountResults({ isPending: true, detail: null })

      expect(wrapper.find('[data-slot="results-skeleton"]').exists()).toBe(true)
    })
  })

  describe('a lost scrape', () => {
    it('says the scrape was lost instead of showing the older results', () => {
      const wrapper = mountResults({ isLost: true })
      const lost = wrapper.get('[data-slot="results-lost"]')

      expect(lost.attributes('role')).toBe('status')
      expect(lost.text()).toContain('Lost track of this run. Reload to check it.')
      expect(wrapper.find('[data-slot="job-json-panel"]').exists()).toBe(false)
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

    it('keeps showing the scrape it has over the error', () => {
      const wrapper = mountResults({ errorMessage: 'Scraper down' })

      expect(wrapper.find('[data-slot="results-error"]').exists()).toBe(false)
      expect(wrapper.text()).toContain('ML Engineer')
    })
  })
})

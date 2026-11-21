import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { ScrapeFailure, ScrapeJob } from '@/modules/scrapes/domain/entities/Scrape'
import ScrapeJobList from '@/modules/scrapes/presentation/components/ScrapeJobList.vue'

function makeJob(overrides: Partial<ScrapeJob> = {}): ScrapeJob {
  return {
    site: 'jobstreet',
    matchedKeyword: 'AI Engineering',
    title: 'ML Engineer',
    company: 'Acme',
    location: 'Remote',
    url: 'https://example.com/1',
    postedAt: '2 days ago',
    salary: null,
    workType: null,
    employmentType: null,
    experienceLevel: null,
    description: null,
    json: { title: 'ML Engineer' },
    ...overrides,
  }
}

const JOBS: ScrapeJob[] = [
  makeJob(),
  makeJob({
    site: 'indeed',
    matchedKeyword: 'Vue',
    title: null,
    company: null,
    location: 'Jakarta',
    url: null,
    postedAt: null,
    json: { location: 'Jakarta' },
  }),
]

const FIVE_JOBS: ScrapeJob[] = [1, 2, 3, 4, 5].map((number) =>
  makeJob({ title: `Job ${number}`, url: `https://example.com/${number}` }),
)

const ASIDE = '<p data-slot="aside-probe">panel</p>'

const FAILURES: ScrapeFailure[] = [
  { keyword: 'Vue', site: 'glints', reason: 'Blocked by the site' },
  { keyword: 'AI Engineering', site: 'linkedin', reason: null },
]

interface Props {
  jobs: ScrapeJob[]
  failures: ScrapeFailure[]
  error: string | null
  selectedIndex: number
}

function mountList(props: Partial<Props> = {}, aside = '') {
  return mount(ScrapeJobList, {
    props: { jobs: JOBS, failures: [], error: null, selectedIndex: 0, ...props },
    slots: aside ? { aside } : {},
    attachTo: document.body,
  })
}

describe('ScrapeJobList', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('shows one row per job with title, company, location, posted and site', () => {
    const wrapper = mountList()
    const rows = wrapper.findAll('[data-slot="job-row"]')

    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain('ML Engineer')
    expect(rows[0]!.text()).toContain('Acme')
    expect(rows[0]!.text()).toContain('Remote')
    expect(rows[0]!.text()).toContain('2 days ago')
    expect(rows[0]!.get('[data-slot="job-site"]').text()).toBe('jobstreet')
  })

  it('links the title to the job in a new tab without an opener', () => {
    const link = mountList().get('[data-slot="job-row"] a')

    expect(link.text()).toContain('ML Engineer')
    expect(link.attributes('href')).toBe('https://example.com/1')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')
  })

  it('marks only the selected job when its JSON shows in the aside', () => {
    const wrapper = mountList({ selectedIndex: 1 }, ASIDE)
    const cards = wrapper.findAll('[data-slot="job-card"]')

    expect(cards[0]!.attributes('data-selected')).toBeUndefined()
    expect(cards[1]!.attributes('data-selected')).toBe('true')
  })

  it('marks no job when there is no aside', () => {
    const wrapper = mountList({ selectedIndex: 1 })

    expect(wrapper.find('[data-slot="job-card"][data-selected]').exists()).toBe(false)
  })

  it('asks to select the job whose card is clicked', async () => {
    const wrapper = mountList()

    await wrapper.findAll('[data-slot="job-card"]')[1]!.trigger('click')

    expect(wrapper.emitted('select')).toEqual([[1]])
  })

  it('shows only the first three jobs with a show more button', () => {
    const wrapper = mountList({ jobs: FIVE_JOBS })
    const toggle = wrapper.get('[data-slot="job-list-toggle"]')

    expect(wrapper.findAll('[data-slot="job-row"]')).toHaveLength(3)
    expect(toggle.text()).toBe('Show 2 more')
    expect(toggle.attributes('aria-expanded')).toBe('false')
  })

  it('shows every job after show more and collapses after show less', async () => {
    const wrapper = mountList({ jobs: FIVE_JOBS })
    const toggle = wrapper.get('[data-slot="job-list-toggle"]')

    await toggle.trigger('click')

    expect(wrapper.findAll('[data-slot="job-row"]')).toHaveLength(5)
    expect(toggle.text()).toBe('Show less')
    expect(toggle.attributes('aria-expanded')).toBe('true')

    await toggle.trigger('click')

    expect(wrapper.findAll('[data-slot="job-row"]')).toHaveLength(3)
  })

  it('asks to select a job revealed by show more', async () => {
    const wrapper = mountList({ jobs: FIVE_JOBS })

    await wrapper.get('[data-slot="job-list-toggle"]').trigger('click')
    await wrapper.findAll('[data-slot="job-card"]')[4]!.trigger('click')

    expect(wrapper.emitted('select')).toEqual([[4]])
  })

  it('collapses again when other jobs are shown', async () => {
    const wrapper = mountList({ jobs: FIVE_JOBS })
    await wrapper.get('[data-slot="job-list-toggle"]').trigger('click')

    await wrapper.setProps({ jobs: [...FIVE_JOBS] })

    expect(wrapper.findAll('[data-slot="job-row"]')).toHaveLength(3)
  })

  it('shows no show more button with three jobs or fewer', () => {
    const wrapper = mountList({ jobs: FIVE_JOBS.slice(0, 3) })

    expect(wrapper.findAll('[data-slot="job-row"]')).toHaveLength(3)
    expect(wrapper.find('[data-slot="job-list-toggle"]').exists()).toBe(false)
  })

  it('shows the aside next to the jobs', () => {
    const wrapper = mountList({}, ASIDE)
    const aside = wrapper.get('[data-slot="job-aside"]')

    expect(aside.element.tagName).toBe('ASIDE')
    expect(aside.attributes('aria-label')).toBe('Selected job JSON')
    expect(aside.find('[data-slot="aside-probe"]').exists()).toBe(true)
  })

  it('shows no aside when the scrape found no jobs', () => {
    const wrapper = mountList({ jobs: [] }, ASIDE)

    expect(wrapper.find('[data-slot="job-aside"]').exists()).toBe(false)
    expect(wrapper.find('[data-slot="aside-probe"]').exists()).toBe(false)
  })

  it('shows no aside when none is given', () => {
    expect(mountList().find('[data-slot="job-aside"]').exists()).toBe(false)
  })

  it('keys same site and keyword failures apart', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const other: ScrapeFailure = { keyword: 'Go', site: 'indeed', reason: null }
    const twice: ScrapeFailure[] = [
      { keyword: 'Vue', site: 'glints', reason: 'Blocked' },
      { keyword: 'Vue', site: 'glints', reason: 'Timed out' },
    ]
    const wrapper = mountList({ failures: [other, ...twice] })

    await wrapper.setProps({ failures: [...twice, other] })

    expect(wrapper.findAll('[data-slot="scrape-failure"]')).toHaveLength(3)
    expect(warn.mock.calls.flat().join(' ')).not.toContain('Duplicate keys')
    warn.mockRestore()
  })

  it('shows a plain title when the job has no link', () => {
    const row = mountList().findAll('[data-slot="job-row"]')[1]!

    expect(row.find('a').exists()).toBe(false)
    expect(row.text()).toContain('Untitled job')
    expect(row.text()).toContain('Jakarta')
  })

  it('lists failed sites before the jobs with their reason when there is one', () => {
    const wrapper = mountList({ failures: FAILURES })
    const failures = wrapper.findAll('[data-slot="scrape-failure"]')

    expect(failures.map((node) => node.text())).toEqual([
      expect.stringContaining('glints'),
      expect.stringContaining('linkedin'),
    ])
    expect(failures[0]!.text()).toContain('Vue')
    expect(failures[0]!.text()).toContain('Blocked by the site')
    expect(failures[1]!.text()).not.toContain(':')

    const html = wrapper.html()
    expect(html.indexOf('data-slot="scrape-failure"')).toBeLessThan(
      html.indexOf('data-slot="job-row"'),
    )
  })

  it('shows no failure list when every site worked', () => {
    expect(mountList().find('[aria-label="Failed sites"]').exists()).toBe(false)
  })

  it('shows the scrape error above the jobs', () => {
    const wrapper = mountList({ jobs: [], error: 'Scraper crashed' })

    expect(wrapper.get('[data-slot="scrape-error"]').text()).toContain('Scraper crashed')
  })

  it('shows an empty state when the scrape found no jobs', () => {
    const wrapper = mountList({ jobs: [], failures: FAILURES })

    expect(wrapper.get('[data-slot="empty-state"]').text()).toContain('No jobs found')
    expect(wrapper.find('[data-slot="job-row"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-slot="scrape-failure"]')).toHaveLength(2)
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { RunFailure, RunJob } from '@/modules/runs/domain/entities/Run'
import RunJobList from '@/modules/runs/presentation/components/RunJobList.vue'

function makeJob(overrides: Partial<RunJob> = {}): RunJob {
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

const JOBS: RunJob[] = [
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

const ASIDE = '<p data-slot="aside-probe">panel</p>'

const FAILURES: RunFailure[] = [
  { keyword: 'Vue', site: 'glints', reason: 'Blocked by the site' },
  { keyword: 'AI Engineering', site: 'linkedin', reason: null },
]

interface Props {
  jobs: RunJob[]
  failures: RunFailure[]
  error: string | null
  selectedIndex: number
}

function mountList(props: Partial<Props> = {}, aside = '') {
  return mount(RunJobList, {
    props: { jobs: JOBS, failures: [], error: null, selectedIndex: 0, ...props },
    slots: aside ? { aside } : {},
    attachTo: document.body,
  })
}

describe('RunJobList', () => {
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
    const buttons = wrapper.findAll('[data-slot="job-json"]')

    expect(cards[0]!.attributes('data-selected')).toBeUndefined()
    expect(cards[1]!.attributes('data-selected')).toBe('true')
    expect(buttons[1]!.attributes('aria-pressed')).toBe('true')
    expect(buttons[1]!.attributes('aria-haspopup')).toBeUndefined()
  })

  it('marks no job and offers the JSON in a dialog when there is no aside', () => {
    const wrapper = mountList({ selectedIndex: 1 })
    const buttons = wrapper.findAll('[data-slot="job-json"]')

    expect(wrapper.find('[data-slot="job-card"][data-selected]').exists()).toBe(false)
    expect(buttons[1]!.attributes('aria-pressed')).toBeUndefined()
    expect(buttons[1]!.attributes('aria-haspopup')).toBe('dialog')
  })

  it('asks to select the job whose card is clicked', async () => {
    const wrapper = mountList()

    await wrapper.findAll('[data-slot="job-card"]')[1]!.trigger('click')

    expect(wrapper.emitted('select')).toEqual([[1]])
  })

  it('asks for the JSON of the job whose JSON button is clicked', async () => {
    const wrapper = mountList()

    await wrapper.findAll('[data-slot="job-json"]')[1]!.trigger('click')

    expect(wrapper.emitted('json')).toEqual([[1]])
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('shows the aside next to the jobs', () => {
    const wrapper = mountList({}, ASIDE)
    const aside = wrapper.get('[data-slot="job-aside"]')

    expect(aside.element.tagName).toBe('ASIDE')
    expect(aside.attributes('aria-label')).toBe('Selected job JSON')
    expect(aside.find('[data-slot="aside-probe"]').exists()).toBe(true)
  })

  it('shows no aside when the run found no jobs', () => {
    const wrapper = mountList({ jobs: [] }, ASIDE)

    expect(wrapper.find('[data-slot="job-aside"]').exists()).toBe(false)
    expect(wrapper.find('[data-slot="aside-probe"]').exists()).toBe(false)
  })

  it('shows no aside when none is given', () => {
    expect(mountList().find('[data-slot="job-aside"]').exists()).toBe(false)
  })

  it('keys same site and keyword failures apart', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const other: RunFailure = { keyword: 'Go', site: 'indeed', reason: null }
    const twice: RunFailure[] = [
      { keyword: 'Vue', site: 'glints', reason: 'Blocked' },
      { keyword: 'Vue', site: 'glints', reason: 'Timed out' },
    ]
    const wrapper = mountList({ failures: [other, ...twice] })

    await wrapper.setProps({ failures: [...twice, other] })

    expect(wrapper.findAll('[data-slot="run-failure"]')).toHaveLength(3)
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
    const failures = wrapper.findAll('[data-slot="run-failure"]')

    expect(failures.map((node) => node.text())).toEqual([
      expect.stringContaining('glints'),
      expect.stringContaining('linkedin'),
    ])
    expect(failures[0]!.text()).toContain('Vue')
    expect(failures[0]!.text()).toContain('Blocked by the site')
    expect(failures[1]!.text()).not.toContain(':')

    const html = wrapper.html()
    expect(html.indexOf('data-slot="run-failure"')).toBeLessThan(
      html.indexOf('data-slot="job-row"'),
    )
  })

  it('shows no failure list when every site worked', () => {
    expect(mountList().find('[aria-label="Failed sites"]').exists()).toBe(false)
  })

  it('shows the run error above the jobs', () => {
    const wrapper = mountList({ jobs: [], error: 'Scraper crashed' })

    expect(wrapper.get('[data-slot="run-error"]').text()).toContain('Scraper crashed')
  })

  it('shows an empty state when the run found no jobs', () => {
    const wrapper = mountList({ jobs: [], failures: FAILURES })

    expect(wrapper.get('[data-slot="empty-state"]').text()).toContain('No jobs found')
    expect(wrapper.find('[data-slot="job-row"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-slot="run-failure"]')).toHaveLength(2)
  })
})

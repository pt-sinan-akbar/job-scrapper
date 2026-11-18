import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { RunFailure, RunJob } from '@/modules/runs/domain/entities/Run'
import RunJobList from '@/modules/runs/presentation/components/RunJobList.vue'

const JOBS: RunJob[] = [
  {
    site: 'jobstreet',
    matchedKeyword: 'AI Engineering',
    title: 'ML Engineer',
    company: 'Acme',
    location: 'Remote',
    url: 'https://example.com/1',
    postedAt: '2 days ago',
  },
  {
    site: 'indeed',
    matchedKeyword: 'Vue',
    title: null,
    company: null,
    location: 'Jakarta',
    url: null,
    postedAt: null,
  },
]

const FAILURES: RunFailure[] = [
  { keyword: 'Vue', site: 'glints', reason: 'Blocked by the site' },
  { keyword: 'AI Engineering', site: 'linkedin', reason: null },
]

function mountList(
  props: { jobs?: RunJob[]; failures?: RunFailure[]; error?: string | null } = {},
) {
  return mount(RunJobList, {
    props: { jobs: JOBS, failures: [], error: null, ...props },
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

  it('tells screen readers the link opens in a new tab', () => {
    const link = mountList().get('[data-slot="job-row"] a')

    expect(link.get('.sr-only').text()).toBe('(opens in new tab)')
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

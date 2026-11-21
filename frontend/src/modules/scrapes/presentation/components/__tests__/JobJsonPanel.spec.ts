import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import type { ScrapeJob } from '@/modules/scrapes/domain/entities/Scrape'
import JobJsonPanel from '@/modules/scrapes/presentation/components/JobJsonPanel.vue'
import JsonViewer from '@/modules/scrapes/presentation/components/JsonViewer.vue'

function jobOf(overrides: Partial<ScrapeJob> = {}): ScrapeJob {
  return {
    site: 'upwork',
    matchedKeyword: 'django',
    title: 'Django dev',
    company: 'Acme',
    location: 'Remote',
    url: 'https://example.com/1',
    postedAt: null,
    salary: null,
    workType: null,
    employmentType: null,
    experienceLevel: null,
    description: null,
    json: { site: 'upwork', title: 'Django dev', job_id: 123, tags: ['python'] },
    ...overrides,
  }
}

function mountPanel(job: ScrapeJob | null) {
  return mount(JobJsonPanel, { props: { job }, attachTo: document.body })
}

describe('JobJsonPanel', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('marks its root so the parent can place it', () => {
    const wrapper = mountPanel(jobOf())

    expect(wrapper.attributes('data-slot')).toBe('job-json-panel')
  })

  it('is a flex column that fills the parent height, with no width or sticky position', () => {
    const classes = mountPanel(jobOf()).classes()

    expect(classes).toEqual(expect.arrayContaining(['flex', 'flex-col', 'h-full', 'min-h-0']))
    expect(classes.join(' ')).not.toMatch(/sticky|(^|\s)(w-|max-w-|top-)/)
  })

  it('shows only a JSON label in the header, with no job title', () => {
    const wrapper = mountPanel(jobOf())
    const header = wrapper.get('[data-slot="json-header"]')

    expect(header.text()).toBe('JSON')
  })

  it('shows the full job json, not only the display fields', () => {
    const job = jobOf()
    const wrapper = mountPanel(job)

    expect(wrapper.getComponent(JsonViewer).props('value')).toEqual(job.json)
    expect(JSON.parse(wrapper.get('pre').text())).toEqual(job.json)
  })

  it('names the JSON region after the job', () => {
    const wrapper = mountPanel(jobOf())

    expect(wrapper.get('[role="region"]').attributes('aria-label')).toBe('Django dev JSON')
  })

  it('passes on the fullscreen request from the viewer', async () => {
    const wrapper = mountPanel(jobOf())

    await wrapper.get('button[data-slot="json-fullscreen"]').trigger('click')

    expect(wrapper.emitted('fullscreen')).toHaveLength(1)
  })

  it('shows the json of the next job when the selection changes', async () => {
    const wrapper = mountPanel(jobOf())

    await wrapper.setProps({ job: jobOf({ title: 'Vue dev', json: { title: 'Vue dev' } }) })

    expect(wrapper.get('[role="region"]').attributes('aria-label')).toBe('Vue dev JSON')
    expect(JSON.parse(wrapper.get('pre').text())).toEqual({ title: 'Vue dev' })
  })

  it('shows a dashed hint and no viewer when no job is selected', () => {
    const wrapper = mountPanel(null)
    const hint = wrapper.get('[data-slot="json-empty"]')

    expect(hint.text()).toBe('Select a job to see its JSON')
    expect(hint.classes()).toContain('border-dashed')
    expect(wrapper.attributes('data-slot')).toBe('job-json-panel')
    expect(wrapper.find('pre').exists()).toBe(false)
    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.find('[data-slot="json-header"]').exists()).toBe(false)
  })

  it('goes back to the hint when the selection is cleared', async () => {
    const wrapper = mountPanel(jobOf())

    await wrapper.setProps({ job: null })

    expect(wrapper.find('[data-slot="json-empty"]').exists()).toBe(true)
    expect(wrapper.find('pre').exists()).toBe(false)
  })
})

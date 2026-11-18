import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import type { RunPayload } from '@/modules/runs/domain/entities/Run'
import RunJsonPanel from '@/modules/runs/presentation/components/RunJsonPanel.vue'

const PAYLOADS: RunPayload[] = [
  {
    keyword: 'AI Engineering',
    site: 'jobstreet',
    raw: { source: 'raw-jobstreet-ai', items: [1, 2, 3] },
    filtered: { source: 'filtered-jobstreet-ai', count: 2, jobs: [{}, {}] },
  },
  {
    keyword: 'Vue',
    site: 'indeed',
    raw: { source: 'raw-indeed-vue' },
    filtered: null,
  },
]

function mountPanel(payloads: RunPayload[] = PAYLOADS) {
  return mount(RunJsonPanel, { props: { payloads }, attachTo: document.body })
}

type Wrapper = ReturnType<typeof mountPanel>

function chips(wrapper: Wrapper) {
  return wrapper.findAll('[data-slot="payload-chip"]')
}

function block(wrapper: Wrapper, field: 'filtered' | 'raw') {
  return wrapper.get(`[data-slot="json-${field}"]`)
}

describe('RunJsonPanel', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('labels a chip per site and keyword and picks the first one', () => {
    const wrapper = mountPanel()

    expect(chips(wrapper).map((node) => node.text())).toEqual([
      'jobstreet · AI Engineering',
      'indeed · Vue',
    ])
    expect(chips(wrapper).map((node) => node.attributes('aria-pressed'))).toEqual(['true', 'false'])
  })

  it('shows the filtered payload first and the raw payload below it', () => {
    const wrapper = mountPanel()

    expect(block(wrapper, 'filtered').get('pre').text()).toContain('filtered-jobstreet-ai')
    expect(block(wrapper, 'raw').get('pre').text()).toContain('raw-jobstreet-ai')
    const html = wrapper.html()
    expect(html.indexOf('json-filtered')).toBeLessThan(html.indexOf('json-raw'))
  })

  it('names each JSON box by what it holds', () => {
    const wrapper = mountPanel()

    expect(block(wrapper, 'filtered').get('[role="region"]').attributes('aria-label')).toBe(
      'Filtered JSON',
    )
    expect(block(wrapper, 'raw').get('[role="region"]').attributes('aria-label')).toBe('Raw JSON')
  })

  it('keeps the JSON read only', () => {
    const wrapper = mountPanel()

    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(wrapper.find('[contenteditable="true"]').exists()).toBe(false)
  })

  it('shows the job count of the filtered payload', () => {
    const wrapper = mountPanel()

    expect(block(wrapper, 'filtered').get('[data-slot="json-count"]').text()).toBe('2 jobs')
  })

  it('switches both payloads when another chip is picked', async () => {
    const wrapper = mountPanel()

    await chips(wrapper)[1]!.trigger('click')

    expect(block(wrapper, 'raw').get('pre').text()).toContain('raw-indeed-vue')
    expect(block(wrapper, 'filtered').text()).toContain('Filtered data was not saved')
    expect(chips(wrapper).map((node) => node.attributes('aria-pressed'))).toEqual(['false', 'true'])
  })

  it('falls back to the first payload when the picked one is gone', async () => {
    const wrapper = mountPanel()
    await chips(wrapper)[1]!.trigger('click')

    await wrapper.setProps({ payloads: [PAYLOADS[0]!] })

    expect(block(wrapper, 'raw').get('pre').text()).toContain('raw-jobstreet-ai')
    expect(chips(wrapper).map((node) => node.attributes('aria-pressed'))).toEqual(['true'])
  })

  it('shows a raw array and counts its items', () => {
    const wrapper = mountPanel([
      { keyword: 'Vue', site: 'indeed', raw: [{ title: 'array-job' }, {}], filtered: null },
    ])

    expect(block(wrapper, 'raw').get('pre').text()).toContain('array-job')
    expect(block(wrapper, 'raw').get('[data-slot="json-count"]').text()).toBe('2 jobs')
  })

  it('shows the filtered data and a missing note when raw was left out', () => {
    const wrapper = mountPanel([
      { keyword: 'Vue', site: 'indeed', raw: null, filtered: { source: 'only-filtered' } },
    ])

    expect(block(wrapper, 'filtered').get('pre').text()).toContain('only-filtered')
    expect(block(wrapper, 'raw').get('[data-slot="json-missing"]').text()).toContain(
      'Raw data was not saved',
    )
  })

  it('says no JSON was saved when the run has no payloads', () => {
    const wrapper = mountPanel([])

    expect(wrapper.text()).toContain('No JSON was saved for this run')
    expect(wrapper.find('pre').exists()).toBe(false)
    expect(wrapper.find('[data-slot="payload-chip"]').exists()).toBe(false)
  })
})

import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { ScrapeJob } from '@/modules/scrapes/domain/entities/Scrape'
import JobJsonDialog from '@/modules/scrapes/presentation/components/JobJsonDialog.vue'

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

async function mountDialog(job: ScrapeJob | null, open = true) {
  const wrapper = mount(JobJsonDialog, { props: { job, open }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

function dialog(): HTMLElement | null {
  return document.body.querySelector<HTMLElement>('[role="dialog"]')
}

function within(selector: string): HTMLElement {
  const node = dialog()?.querySelector<HTMLElement>(selector)
  if (!node) {
    throw new Error(`Nothing in the dialog matches ${selector}`)
  }
  return node
}

function describedBy(): string {
  const id = dialog()!.getAttribute('aria-describedby')
  return document.getElementById(id ?? '')?.textContent?.trim() ?? ''
}

function labelledBy(): string {
  const id = dialog()!.getAttribute('aria-labelledby')
  return document.getElementById(id ?? '')?.textContent?.trim() ?? ''
}

describe('JobJsonDialog', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('shows nothing while it is closed', async () => {
    await mountDialog(jobOf(), false)

    expect(dialog()).toBeNull()
  })

  it('opens a dialog titled with the job title', async () => {
    await mountDialog(jobOf())

    expect(within('[data-slot="dialog-title"]').textContent?.trim()).toBe('Django dev')
    expect(labelledBy()).toBe('Django dev')
  })

  it('says Untitled job when the job has no title', async () => {
    await mountDialog(jobOf({ title: null }))

    expect(labelledBy()).toBe('Untitled job')
  })

  it('describes itself for screen readers without showing the description', async () => {
    await mountDialog(jobOf())

    expect(describedBy()).toBe('Full JSON of this job')
    expect(within('[data-slot="dialog-description"]').classList.contains('sr-only')).toBe(true)
  })

  it('covers almost the whole viewport', async () => {
    await mountDialog(jobOf())
    const classes = dialog()!.className

    expect(classes).toContain('inset-x-[2.5vw]')
    expect(classes).toContain('h-[90dvh]')
    expect(classes).toContain('max-h-[90dvh]')
    expect(classes).toContain('max-w-none')
    expect(classes).not.toContain('max-w-120')
    expect(classes).not.toContain('inset-x-4')
  })

  it('scrolls inside the JSON box, not the dialog', async () => {
    await mountDialog(jobOf())

    expect(dialog()!.className).toContain('overflow-hidden')
    expect(dialog()!.className).not.toContain('overflow-y-auto')
    expect(within('[data-slot="json-scroll"]').classList.contains('overflow-auto')).toBe(true)
  })

  it('shows the full job json', async () => {
    const job = jobOf()
    await mountDialog(job)

    expect(JSON.parse(within('pre').textContent ?? '')).toEqual(job.json)
    expect(within('[role="region"]').getAttribute('aria-label')).toBe('Django dev JSON')
  })

  it('offers copy but no fullscreen button', async () => {
    await mountDialog(jobOf())

    expect(dialog()!.querySelector('[data-slot="json-copy"]')).not.toBeNull()
    expect(dialog()!.querySelector('[data-slot="json-fullscreen"]')).toBeNull()
  })

  it('asks to close from the close button', async () => {
    const wrapper = await mountDialog(jobOf())

    within('button[aria-label="Close"]').click()
    await flushPromises()

    expect(wrapper.emitted('update:open')).toEqual([[false]])
  })

  it('asks to close on Escape', async () => {
    const wrapper = await mountDialog(jobOf())

    dialog()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()

    expect(wrapper.emitted('update:open')).toEqual([[false]])
  })

  it('goes away when the parent closes it', async () => {
    const wrapper = await mountDialog(jobOf())

    await wrapper.setProps({ open: false })
    await flushPromises()

    expect(dialog()).toBeNull()
  })

  it('shows a hint instead of JSON when it is open with no job', async () => {
    await mountDialog(null)

    expect(labelledBy()).toBe('Untitled job')
    expect(within('[data-slot="json-empty"]').textContent?.trim()).toBe('No job selected')
    expect(dialog()!.querySelector('pre')).toBeNull()
  })
})

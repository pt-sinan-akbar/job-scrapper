import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { ScrapeRecord } from '@/modules/scrapes/domain/entities/Scrape'
import ScrapeProgressOverlay from '@/modules/scrapes/presentation/components/ScrapeProgressOverlay.vue'

function runningRecord(overrides: Partial<ScrapeRecord> = {}): ScrapeRecord {
  return {
    id: 'run-1',
    status: 'running',
    keywords: ['AI Engineer', 'Python'],
    sites: ['jobstreet', 'glints'],
    startedAt: new Date().toISOString(),
    finishedAt: null,
    jobCount: 0,
    errorCount: 0,
    error: null,
    discordStatus: null,
    discordSent: 0,
    discordFailed: 0,
    discordError: null,
    ...overrides,
  }
}

async function mountOverlay(record: ScrapeRecord | null, isHidden = false) {
  const wrapper = mount(ScrapeProgressOverlay, {
    props: { record, isHidden },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

function overlay(): HTMLElement | null {
  return document.body.querySelector<HTMLElement>('[data-slot="scrape-progress-overlay"]')
}

function textOf(selector: string): string {
  return overlay()?.querySelector(selector)?.textContent?.trim() ?? ''
}

describe('ScrapeProgressOverlay', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('covers the screen with the scrape progress while a scrape runs', async () => {
    await mountOverlay(runningRecord())

    expect(overlay()?.getAttribute('role')).toBe('dialog')
    expect(textOf('[data-slot="scrape-overlay-title"]')).toBe('Scraping 2 sites')
    expect(textOf('[data-slot="scrape-overlay-keywords"]')).toBe('AI Engineer, Python')
    expect(textOf('[data-slot="scrape-overlay-elapsed"]')).toBe('00:00')
  })

  it('lists every site being scraped', async () => {
    await mountOverlay(runningRecord())

    const sites = [...overlay()!.querySelectorAll('li')].map((item) => item.textContent?.trim())
    expect(sites).toEqual(['jobstreet', 'glints'])
  })

  it('shows nothing when no scrape runs', async () => {
    await mountOverlay(null)

    expect(overlay()).toBeNull()
  })

  it('shows nothing once the user hid it', async () => {
    await mountOverlay(runningRecord(), true)

    expect(overlay()).toBeNull()
  })

  it('asks to hide when Keep browsing is clicked', async () => {
    const wrapper = await mountOverlay(runningRecord())

    overlay()!.querySelector<HTMLButtonElement>('[data-slot="scrape-overlay-hide"]')!.click()
    await flushPromises()

    expect(wrapper.emitted('hide')).toHaveLength(1)
  })

  it('asks to hide when Escape is pressed', async () => {
    const wrapper = await mountOverlay(runningRecord())

    overlay()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()

    expect(wrapper.emitted('hide')).toHaveLength(1)
  })
})

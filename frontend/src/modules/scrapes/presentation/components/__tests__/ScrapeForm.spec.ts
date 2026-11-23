import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, RouterLinkStub } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createMemoryStorage } from '@/__tests__/memoryStorage'
import type {
  ScrapeOptions,
  ScrapeRecord,
  ScrapeStatus,
} from '@/modules/scrapes/domain/entities/Scrape'
import type { NotifyDiscordBlock } from '@/modules/scrapes/presentation/components/notifyDiscordBlock'
import ScrapeForm from '@/modules/scrapes/presentation/components/ScrapeForm.vue'
import { NOTIFY_DISCORD_STORAGE_KEY } from '@/modules/scrapes/presentation/components/notifyDiscordStorage'

const OPTIONS: ScrapeOptions = {
  sites: [
    { name: 'upwork', isEnabled: true },
    { name: 'indeed', isEnabled: false },
  ],
  isStale: false,
}

type Props = {
  isScraping?: boolean
  discordBlock?: NotifyDiscordBlock | null
  hasUnsavedConfig?: boolean
  latestScrape?: ScrapeRecord | null
}

const UNCHANGED_HINT = 'Change keywords or sites to scrape again'

function latestScrapeOf(
  status: ScrapeStatus,
  keywords: string[] = ['django', 'vue'],
  sites: string[] = ['upwork'],
): ScrapeRecord {
  return {
    id: 'scrape-1',
    status,
    keywords,
    sites,
    startedAt: '2026-11-01T10:00:00+00:00',
    finishedAt: '2026-11-01T10:01:00+00:00',
    jobCount: 3,
    errorCount: 0,
    error: null,
    discordStatus: null,
    discordSent: 0,
    discordFailed: 0,
    discordError: null,
  }
}

function mountForm(props: Props = {}) {
  return mount(ScrapeForm, {
    props: { options: OPTIONS, isScraping: false, discordBlock: null, ...props },
    global: { stubs: { RouterLink: RouterLinkStub } },
    attachTo: document.body,
  })
}

type Wrapper = ReturnType<typeof mountForm>

function notifyBox(wrapper: Wrapper) {
  return wrapper.get('#scrape-notify-discord')
}

function scrapeButton(wrapper: Wrapper) {
  return wrapper.get('[data-slot="scrape-start"]')
}

function keywordBox(wrapper: Wrapper) {
  return wrapper.get('#scrape-keywords')
}

function keywordChips(wrapper: Wrapper): string[] {
  return wrapper.findAll('[data-slot="keyword-chip"]').map((chip) => chip.text())
}

async function clickStart(wrapper: Wrapper) {
  await scrapeButton(wrapper).trigger('click')
}

async function pressKey(wrapper: Wrapper, key: string): Promise<KeyboardEvent> {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
  keywordBox(wrapper).element.dispatchEvent(event)
  await nextTick()
  return event
}

async function addKeyword(wrapper: Wrapper, keyword: string) {
  await keywordBox(wrapper).setValue(keyword)
  await pressKey(wrapper, 'Enter')
}

async function pasteKeywords(wrapper: Wrapper, pastedText: string): Promise<Event> {
  const event = new Event('paste', { bubbles: true, cancelable: true })
  Object.defineProperty(event, 'clipboardData', { value: { getData: () => pastedText } })
  keywordBox(wrapper).element.dispatchEvent(event)
  await nextTick()
  return event
}

function buildKeywordList(count: number): string[] {
  return Array.from({ length: count }, (_, index) => `keyword ${index + 1}`)
}

async function typeKeywords(wrapper: Wrapper) {
  await wrapper.get('#scrape-keywords').setValue('django, vue')
}

function siteBox(wrapper: Wrapper, name: string) {
  return wrapper.get(`#site-${name}`)
}

function unchangedHint(wrapper: Wrapper) {
  return wrapper.find('#scrape-unchanged-hint')
}

async function addKeywordCount(wrapper: Wrapper, count: number) {
  for (const keyword of buildKeywordList(count)) {
    await addKeyword(wrapper, keyword)
  }
}

describe('ScrapeForm', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createMemoryStorage())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('has the Send to Discord checkbox, off by default', () => {
    const wrapper = mountForm()

    expect(wrapper.get('label[for="scrape-notify-discord"]').text()).toBe('Send to Discord')
    expect(wrapper.text()).not.toContain('when done')
    expect(notifyBox(wrapper).attributes('data-state')).toBe('unchecked')
    expect(notifyBox(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('puts Send to Discord on the left and the sites on the right of one row', () => {
    const row = mountForm().get('[data-slot="scrape-options"]')
    const [discord, sites] = row.element.children

    expect(row.classes()).toEqual(expect.arrayContaining(['flex-col', 'sm:flex-row']))
    expect(row.classes()).toContain('sm:justify-between')
    expect(discord!.querySelector('#scrape-notify-discord')).not.toBeNull()
    expect(sites!.tagName).toBe('FIELDSET')
    expect(sites!.querySelector('[data-slot="site-options"]')!.className).toContain(
      'sm:justify-end',
    )
  })

  it('keeps the Sites group name for screen readers only', () => {
    const wrapper = mountForm()

    const legend = wrapper.get('legend')
    expect(legend.text()).toBe('Sites')
    expect(legend.classes()).toContain('sr-only')
  })

  it('emits start with notify false by default', async () => {
    const wrapper = mountForm()
    await typeKeywords(wrapper)

    await clickStart(wrapper)

    expect(wrapper.emitted('start')).toEqual([[['django', 'vue'], ['upwork'], false]])
  })

  it('emits start with notify true once the box is checked', async () => {
    const wrapper = mountForm()
    await typeKeywords(wrapper)

    await notifyBox(wrapper).trigger('click')
    await clickStart(wrapper)

    expect(wrapper.emitted('start')).toEqual([[['django', 'vue'], ['upwork'], true]])
  })

  it('remembers the choice', async () => {
    const wrapper = mountForm()

    await notifyBox(wrapper).trigger('click')

    expect(localStorage.getItem(NOTIFY_DISCORD_STORAGE_KEY)).toBe('true')
    wrapper.unmount()
    expect(notifyBox(mountForm()).attributes('data-state')).toBe('checked')
  })

  describe('when Discord cannot be used', () => {
    it.each<[NotifyDiscordBlock, string]>([
      ['not-configured', 'Save a bot token on the Discord page'],
      ['no-channel', 'Set a default channel on the Discord page'],
    ])('disables the checkbox and says what to do for %s', (discordBlock, hint) => {
      const wrapper = mountForm({ discordBlock })

      expect(notifyBox(wrapper).attributes('disabled')).toBeDefined()
      expect(wrapper.text()).toContain(hint)
    })

    it.each<NotifyDiscordBlock>(['not-configured', 'no-channel'])(
      'links to the Discord page for %s',
      (discordBlock) => {
        const wrapper = mountForm({ discordBlock })

        expect(wrapper.getComponent(RouterLinkStub).props('to')).toBe('/discord')
      },
    )

    it('disables the checkbox but shows no hint while the settings load', () => {
      const wrapper = mountForm({ discordBlock: 'loading' })

      expect(notifyBox(wrapper).attributes('disabled')).toBeDefined()
      expect(wrapper.find('[data-slot="discord-hint"]').exists()).toBe(false)
      expect(wrapper.findComponent(RouterLinkStub).exists()).toBe(false)
    })

    it('says the settings could not load', () => {
      const wrapper = mountForm({ discordBlock: 'load-failed' })

      expect(notifyBox(wrapper).attributes('disabled')).toBeDefined()
      expect(wrapper.text()).toContain('Could not load Discord settings')
    })

    it('shows no hint or link when Discord is ready', () => {
      const wrapper = mountForm()

      expect(wrapper.find('[data-slot="discord-hint"]').exists()).toBe(false)
      expect(wrapper.findComponent(RouterLinkStub).exists()).toBe(false)
    })

    it('shows the box unchecked even when it was remembered on', () => {
      localStorage.setItem(NOTIFY_DISCORD_STORAGE_KEY, 'true')

      const wrapper = mountForm({ discordBlock: 'no-channel' })

      expect(notifyBox(wrapper).attributes('data-state')).toBe('unchecked')
    })

    it('emits start with notify false even when it was remembered on', async () => {
      localStorage.setItem(NOTIFY_DISCORD_STORAGE_KEY, 'true')
      const wrapper = mountForm({ discordBlock: 'no-channel' })
      await typeKeywords(wrapper)

      await clickStart(wrapper)

      expect(wrapper.emitted('start')).toEqual([[['django', 'vue'], ['upwork'], false]])
    })
  })

  describe('unsaved config', () => {
    it('lets the scrape start by default', async () => {
      const wrapper = mountForm()
      await typeKeywords(wrapper)

      expect(scrapeButton(wrapper).attributes('disabled')).toBeUndefined()
      expect(wrapper.text()).not.toContain('Save or discard config changes first')
    })

    it('blocks Run scrape and says why', async () => {
      const wrapper = mountForm({ hasUnsavedConfig: true })
      await typeKeywords(wrapper)

      expect(scrapeButton(wrapper).attributes('disabled')).toBeDefined()
      expect(wrapper.text()).toContain('Save or discard config changes first')
    })

    it('links to the config card', () => {
      const wrapper = mountForm({ hasUnsavedConfig: true })

      expect(wrapper.getComponent(RouterLinkStub).props('to')).toEqual({
        path: '/scrapes',
        hash: '#config',
      })
    })
  })

  describe('keyword chips', () => {
    it('adds a chip on Enter without starting the scrape', async () => {
      const wrapper = mountForm()
      await keywordBox(wrapper).setValue(' django ')

      const event = await pressKey(wrapper, 'Enter')

      expect(event.defaultPrevented).toBe(true)
      expect(keywordChips(wrapper)).toEqual(['django'])
      expect((keywordBox(wrapper).element as HTMLInputElement).value).toBe('')
      expect(wrapper.emitted('start')).toBeUndefined()
    })

    it('does nothing on Enter with no text', async () => {
      const wrapper = mountForm()

      const event = await pressKey(wrapper, 'Enter')

      expect(event.defaultPrevented).toBe(true)
      expect(keywordChips(wrapper)).toEqual([])
      expect(wrapper.find('ul[aria-label="Keywords"]').exists()).toBe(false)
    })

    it('adds a chip on comma', async () => {
      const wrapper = mountForm()
      await keywordBox(wrapper).setValue('django')

      const event = await pressKey(wrapper, ',')

      expect(event.defaultPrevented).toBe(true)
      expect(keywordChips(wrapper)).toEqual(['django'])
      expect((keywordBox(wrapper).element as HTMLInputElement).value).toBe('')
    })

    it('splits pasted text into chips', async () => {
      const wrapper = mountForm()

      const event = await pasteKeywords(wrapper, 'a, b, c')

      expect(event.defaultPrevented).toBe(true)
      expect(keywordChips(wrapper)).toEqual(['a', 'b', 'c'])
    })

    it('lists the chips for screen readers', async () => {
      const wrapper = mountForm()

      await addKeyword(wrapper, 'django')

      const list = wrapper.get('ul[aria-label="Keywords"]')
      expect(list.findAll('li')).toHaveLength(1)
      expect(wrapper.find('label[for="scrape-keywords"]').exists()).toBe(true)
    })

    it('removes a chip with its x button', async () => {
      const wrapper = mountForm()
      await addKeyword(wrapper, 'django')
      await addKeyword(wrapper, 'vue')

      await wrapper.get('button[aria-label="Remove django"]').trigger('click')

      expect(keywordChips(wrapper)).toEqual(['vue'])
      expect(document.activeElement).toBe(keywordBox(wrapper).element)
    })

    it('removes the last chip on Backspace with no text', async () => {
      const wrapper = mountForm()
      await addKeyword(wrapper, 'django')
      await addKeyword(wrapper, 'vue')

      await pressKey(wrapper, 'Backspace')

      expect(keywordChips(wrapper)).toEqual(['django'])
    })

    it('keeps the chips on Backspace while there is text', async () => {
      const wrapper = mountForm()
      await addKeyword(wrapper, 'django')
      await keywordBox(wrapper).setValue('vu')

      await pressKey(wrapper, 'Backspace')

      expect(keywordChips(wrapper)).toEqual(['django'])
    })

    it('ignores a chip that is already there, ignoring case and spaces', async () => {
      const wrapper = mountForm()
      await addKeyword(wrapper, 'Django')

      await addKeyword(wrapper, '  django ')

      expect(keywordChips(wrapper)).toEqual(['Django'])
      expect((keywordBox(wrapper).element as HTMLInputElement).value).toBe('')
    })

    it('keeps Run scrape on below 10 chips with no count hint', async () => {
      const wrapper = mountForm()

      await addKeywordCount(wrapper, 9)

      expect(scrapeButton(wrapper).attributes('disabled')).toBeUndefined()
      expect(wrapper.find('#scrape-keywords-hint').exists()).toBe(false)
      expect(keywordBox(wrapper).attributes('aria-describedby')).toBeUndefined()
    })

    it('refuses an 11th chip and shows the count in muted text', async () => {
      const wrapper = mountForm()
      await addKeywordCount(wrapper, 10)

      await addKeyword(wrapper, 'one more')

      const hint = wrapper.get('#scrape-keywords-hint')
      expect(keywordChips(wrapper)).toHaveLength(10)
      expect(keywordChips(wrapper)).not.toContain('one more')
      expect(hint.text()).toBe('10 / 10 keywords')
      expect(hint.classes()).toContain('text-ink-muted')
      expect(hint.classes()).not.toContain('text-danger')
      expect(scrapeButton(wrapper).attributes('disabled')).toBeUndefined()
    })

    it('ties the count hint to the keywords box', async () => {
      const wrapper = mountForm()

      await addKeywordCount(wrapper, 10)

      expect(keywordBox(wrapper).attributes('aria-describedby')).toBe('scrape-keywords-hint')
    })

    it('includes typed text in the scrape when the button is clicked', async () => {
      const wrapper = mountForm()
      await addKeyword(wrapper, 'django')
      await keywordBox(wrapper).setValue('vue')

      await clickStart(wrapper)

      expect(wrapper.emitted('start')).toEqual([[['django', 'vue'], ['upwork'], false]])
      expect(keywordChips(wrapper)).toEqual(['django', 'vue'])
      expect((keywordBox(wrapper).element as HTMLInputElement).value).toBe('')
    })

    it('leaves typed text out once there are 10 chips', async () => {
      const wrapper = mountForm()
      await addKeywordCount(wrapper, 10)
      await keywordBox(wrapper).setValue('one more')

      await clickStart(wrapper)

      expect(wrapper.emitted('start')).toEqual([[buildKeywordList(10), ['upwork'], false]])
    })

    it('starts the scrape only from the button', async () => {
      const wrapper = mountForm()
      await addKeyword(wrapper, 'django')

      await wrapper.get('form').trigger('submit')

      expect(wrapper.emitted('start')).toBeUndefined()
    })
  })

  describe('after a finished scrape', () => {
    it.each<ScrapeStatus>(['succeeded', 'partial'])(
      'blocks Run scrape for the same keywords and sites after a %s scrape',
      async (status) => {
        const wrapper = mountForm({ latestScrape: latestScrapeOf(status) })

        await typeKeywords(wrapper)

        expect(scrapeButton(wrapper).attributes('disabled')).toBeDefined()
        expect(unchangedHint(wrapper).text()).toBe(UNCHANGED_HINT)
      },
    )

    it('shows the hint in the muted color', async () => {
      const wrapper = mountForm({ latestScrape: latestScrapeOf('succeeded') })

      await typeKeywords(wrapper)

      expect(unchangedHint(wrapper).classes()).toContain('text-ink-muted')
      expect(unchangedHint(wrapper).classes()).not.toContain('text-danger')
    })

    it('ties the hint to the keywords box', async () => {
      const wrapper = mountForm({ latestScrape: latestScrapeOf('succeeded') })

      await typeKeywords(wrapper)

      expect(wrapper.get('#scrape-keywords').attributes('aria-describedby')).toBe(
        'scrape-unchanged-hint',
      )
    })

    it('keeps Run scrape blocked for the same keywords in another order and case', async () => {
      const wrapper = mountForm({ latestScrape: latestScrapeOf('succeeded') })

      await addKeyword(wrapper, 'VUE')
      await addKeyword(wrapper, ' Django ')

      expect(scrapeButton(wrapper).attributes('disabled')).toBeDefined()
      expect(unchangedHint(wrapper).exists()).toBe(true)
    })

    it('does not submit the same keywords and sites', async () => {
      const wrapper = mountForm({ latestScrape: latestScrapeOf('succeeded') })
      await typeKeywords(wrapper)

      await clickStart(wrapper)

      expect(wrapper.emitted('start')).toBeUndefined()
    })

    it('lets the scrape start once a keyword changes', async () => {
      const wrapper = mountForm({ latestScrape: latestScrapeOf('succeeded') })
      await addKeyword(wrapper, 'django')
      await addKeyword(wrapper, 'vue')

      await wrapper.get('button[aria-label="Remove vue"]').trigger('click')
      await addKeyword(wrapper, 'react')

      expect(scrapeButton(wrapper).attributes('disabled')).toBeUndefined()
      expect(unchangedHint(wrapper).exists()).toBe(false)
      expect(wrapper.get('#scrape-keywords').attributes('aria-describedby')).toBeUndefined()
    })

    it('lets the scrape start once a site is added', async () => {
      const wrapper = mountForm({ latestScrape: latestScrapeOf('succeeded') })
      await typeKeywords(wrapper)

      await siteBox(wrapper, 'indeed').trigger('click')

      expect(scrapeButton(wrapper).attributes('disabled')).toBeUndefined()
      expect(unchangedHint(wrapper).exists()).toBe(false)
    })

    it('lets the scrape start once a site is removed', async () => {
      const latestScrape = latestScrapeOf('succeeded', ['django', 'vue'], ['upwork', 'indeed'])
      const wrapper = mountForm({ latestScrape })
      await typeKeywords(wrapper)
      await siteBox(wrapper, 'indeed').trigger('click')
      expect(scrapeButton(wrapper).attributes('disabled')).toBeDefined()

      await siteBox(wrapper, 'indeed').trigger('click')

      expect(scrapeButton(wrapper).attributes('disabled')).toBeUndefined()
      expect(unchangedHint(wrapper).exists()).toBe(false)
    })

    it('lets a failed scrape be tried again with the same input', async () => {
      const wrapper = mountForm({ latestScrape: latestScrapeOf('failed') })

      await typeKeywords(wrapper)

      expect(scrapeButton(wrapper).attributes('disabled')).toBeUndefined()
      expect(unchangedHint(wrapper).exists()).toBe(false)
    })

    it('keeps Run scrape blocked when only Send to Discord changes', async () => {
      const wrapper = mountForm({ latestScrape: latestScrapeOf('succeeded') })
      await typeKeywords(wrapper)

      await notifyBox(wrapper).trigger('click')

      expect(notifyBox(wrapper).attributes('data-state')).toBe('checked')
      expect(scrapeButton(wrapper).attributes('disabled')).toBeDefined()
      expect(unchangedHint(wrapper).exists()).toBe(true)
    })

    it('lets the scrape start once text is typed next to the same chips', async () => {
      const wrapper = mountForm({ latestScrape: latestScrapeOf('succeeded') })
      await addKeyword(wrapper, 'django')
      await addKeyword(wrapper, 'vue')
      expect(scrapeButton(wrapper).attributes('disabled')).toBeDefined()

      await keywordBox(wrapper).setValue('react')

      expect(scrapeButton(wrapper).attributes('disabled')).toBeUndefined()
      expect(unchangedHint(wrapper).exists()).toBe(false)
    })

    it('lets the scrape start when there is no latest scrape', async () => {
      const wrapper = mountForm({ latestScrape: null })

      await typeKeywords(wrapper)

      expect(scrapeButton(wrapper).attributes('disabled')).toBeUndefined()
      expect(unchangedHint(wrapper).exists()).toBe(false)
    })

    it('ties both hints to the keywords box when both show', async () => {
      const keywords = buildKeywordList(10)
      const wrapper = mountForm({ latestScrape: latestScrapeOf('succeeded', keywords) })

      await addKeywordCount(wrapper, 10)

      expect(wrapper.get('#scrape-keywords').attributes('aria-describedby')).toBe(
        'scrape-keywords-hint scrape-unchanged-hint',
      )
    })
  })

  it('blocks Run scrape while a scrape is going', async () => {
    const wrapper = mountForm({ isScraping: true })
    await typeKeywords(wrapper)

    expect(scrapeButton(wrapper).attributes('disabled')).toBeDefined()
    expect(scrapeButton(wrapper).text()).toBe('Scrape running')
  })
})

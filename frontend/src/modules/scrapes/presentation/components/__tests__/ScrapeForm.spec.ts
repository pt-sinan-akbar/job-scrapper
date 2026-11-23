import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, RouterLinkStub } from '@vue/test-utils'
import { createMemoryStorage } from '@/__tests__/memoryStorage'
import type { ScrapeOptions } from '@/modules/scrapes/domain/entities/Scrape'
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
  return wrapper.get('button[type="submit"]')
}

async function typeKeywords(wrapper: Wrapper) {
  await wrapper.get('#scrape-keywords').setValue('django, vue')
}

async function typeKeywordCount(wrapper: Wrapper, count: number) {
  const keywords = Array.from({ length: count }, (_, index) => `keyword ${index + 1}`)
  await wrapper.get('#scrape-keywords').setValue(keywords.join(', '))
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

    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('start')).toEqual([[['django', 'vue'], ['upwork'], false]])
  })

  it('emits start with notify true once the box is checked', async () => {
    const wrapper = mountForm()
    await typeKeywords(wrapper)

    await notifyBox(wrapper).trigger('click')
    await wrapper.get('form').trigger('submit')

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

      await wrapper.get('form').trigger('submit')

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

  describe('keyword limit', () => {
    it('keeps Run scrape on at exactly 10 keywords with no hint', async () => {
      const wrapper = mountForm()

      await typeKeywordCount(wrapper, 10)

      expect(scrapeButton(wrapper).attributes('disabled')).toBeUndefined()
      expect(wrapper.find('#scrape-keywords-hint').exists()).toBe(false)
      expect(wrapper.get('#scrape-keywords').attributes('aria-describedby')).toBeUndefined()
    })

    it('blocks Run scrape past 10 keywords and shows the count', async () => {
      const wrapper = mountForm()

      await typeKeywordCount(wrapper, 11)

      const hint = wrapper.get('#scrape-keywords-hint')
      expect(scrapeButton(wrapper).attributes('disabled')).toBeDefined()
      expect(hint.text()).toBe('11 / 10 keywords')
      expect(hint.classes()).toContain('text-danger')
    })

    it('ties the count hint to the keywords box', async () => {
      const wrapper = mountForm()

      await typeKeywordCount(wrapper, 12)

      expect(wrapper.get('#scrape-keywords').attributes('aria-describedby')).toBe(
        'scrape-keywords-hint',
      )
    })

    it('does not submit past 10 keywords', async () => {
      const wrapper = mountForm()
      await typeKeywordCount(wrapper, 11)

      await wrapper.get('form').trigger('submit')

      expect(wrapper.emitted('start')).toBeUndefined()
    })
  })

  it('blocks Run scrape while a scrape is going', async () => {
    const wrapper = mountForm({ isScraping: true })
    await typeKeywords(wrapper)

    expect(scrapeButton(wrapper).attributes('disabled')).toBeDefined()
    expect(scrapeButton(wrapper).text()).toBe('Scrape running')
  })
})

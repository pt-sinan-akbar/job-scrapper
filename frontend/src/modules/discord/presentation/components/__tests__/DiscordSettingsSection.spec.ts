import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import type { DiscordSettings } from '@/modules/discord/domain/entities/Discord'
import DiscordSettingsSection from '@/modules/discord/presentation/components/DiscordSettingsSection.vue'
import { provideDiscordUseCases } from '@/modules/discord/presentation/stores/discordUseCases'
import type { ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
import { provideConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import type { ScrapeDetail } from '@/modules/scrapes/domain/entities/Scrape'
import { provideScrapeUseCases } from '@/modules/scrapes/presentation/stores/scrapeUseCases'
import { renderMarkdown } from '@/shared/utils/markdown'

const toastSuccess = vi.hoisted(() => vi.fn())

vi.mock('vue-sonner', () => ({ toast: { success: toastSuccess } }))

const getSettings = { execute: vi.fn() }
const saveSettings = { execute: vi.fn() }
const testConnection = { execute: vi.fn() }
const listChannels = { execute: vi.fn() }
const previewMessage = { execute: vi.fn() }
const sendMessage = { execute: vi.fn() }

const getConfig = { execute: vi.fn() }
const saveConfig = { execute: vi.fn() }

const getScrapeOptions = { execute: vi.fn() }
const getScrape = { execute: vi.fn() }
const getLatestScrape = { execute: vi.fn() }
const startScrape = { execute: vi.fn() }
const sendLatestScrapeToDiscord = { execute: vi.fn() }

const LATEST_SCRAPE: ScrapeDetail = {
  record: {
    id: 'run-1',
    status: 'succeeded',
    keywords: ['django'],
    sites: ['upwork'],
    startedAt: '2026-11-01T10:00:00+00:00',
    finishedAt: '2026-11-01T10:01:00+00:00',
    jobCount: 4,
    errorCount: 0,
    error: null,
    discordStatus: null,
    discordSent: 0,
    discordFailed: 0,
    discordError: null,
  },
  jobs: [],
  failures: [],
}

const CONFIG: ConfigSnapshot = {
  values: {
    fields: ['title'],
    sites: [],
  },
  version: 1,
  updatedAt: '2026-11-02T01:00:00+00:00',
  updatedBy: 'ui',
  isStale: false,
  jobFields: ['title', 'company', 'url'],
  mandatoryFields: ['company'],
  locationOptions: [],
}

const SETTINGS: DiscordSettings = {
  isConfigured: true,
  tokenHint: '••••1234',
  defaultChannelId: '12345678901234567',
  mentionUserId: '76543210987654321',
  messageTemplate: '{title} at {company}',
  maxChars: 1900,
  updatedAt: null,
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve: (value: T) => void = () => undefined
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function mountSection(pinia: Pinia = createPinia(), isAttached = true) {
  return mount(DiscordSettingsSection, {
    global: { plugins: [pinia] },
    attachTo: isAttached ? document.body : undefined,
  })
}

function chips(wrapper: ReturnType<typeof mountSection>) {
  return wrapper.findAll('[data-slot="template-variable"]')
}

function inputValue(wrapper: ReturnType<typeof mountSection>, id: string): string {
  return (wrapper.get(id).element as HTMLInputElement).value
}

function button(wrapper: ReturnType<typeof mountSection>, label: string) {
  return wrapper.findAll('button').find((node) => node.text() === label)!
}

function isSaveDisabled(wrapper: ReturnType<typeof mountSection>): boolean {
  return button(wrapper, 'Save').attributes('disabled') !== undefined
}

function previewHtml(wrapper: ReturnType<typeof mountSection>) {
  return wrapper.get('[data-slot="template-preview-html"]')
}

describe('DiscordSettingsSection', () => {
  beforeAll(async () => {
    await renderMarkdown('')
  })

  beforeEach(() => {
    vi.resetAllMocks()
    getSettings.execute.mockResolvedValue(SETTINGS)
    getConfig.execute.mockResolvedValue(CONFIG)
    getLatestScrape.execute.mockResolvedValue(LATEST_SCRAPE)
    provideConfigUseCases({ getConfig, saveConfig })
    provideScrapeUseCases({
      getOptions: getScrapeOptions,
      getScrape,
      getLatestScrape,
      startScrape,
      sendLatestScrapeToDiscord,
    })
    provideDiscordUseCases({
      getSettings,
      saveSettings,
      testConnection,
      listChannels,
      previewMessage,
      sendMessage,
    })
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('shows a skeleton until the settings load', async () => {
    const first = deferred<DiscordSettings>()
    getSettings.execute.mockReturnValue(first.promise)
    const wrapper = mountSection()
    await flushPromises()

    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain('Loading Discord settings')

    first.resolve(SETTINGS)
    await flushPromises()

    expect(wrapper.find('form').exists()).toBe(true)
  })

  it('shows an error with a retry when the settings fail to load', async () => {
    getSettings.execute.mockRejectedValueOnce(new Error('Scraper down'))
    const wrapper = mountSection()
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Scraper down')

    await button(wrapper, 'Try again').trigger('click')
    await flushPromises()

    expect(getSettings.execute).toHaveBeenCalledTimes(2)
    expect(wrapper.find('form').exists()).toBe(true)
  })

  it('fills the form from the saved settings', async () => {
    const wrapper = mountSection()
    await flushPromises()

    expect(inputValue(wrapper, '#discord-default-channel')).toBe('12345678901234567')
    expect(inputValue(wrapper, '#discord-mention-user')).toBe('76543210987654321')
    expect(inputValue(wrapper, '#discord-template')).toBe('{title} at {company}')
    expect(inputValue(wrapper, '#discord-max-chars')).toBe('1900')
  })

  it('puts channel, mention user and max chars in one three column row', async () => {
    const wrapper = mountSection()
    await flushPromises()

    const row = wrapper.get('[data-slot="settings-ids-row"]')
    expect(row.classes()).toContain('sm:grid-cols-3')
    expect(row.findAll('input').map((input) => input.attributes('id'))).toEqual([
      'discord-default-channel',
      'discord-mention-user',
      'discord-max-chars',
    ])
  })

  it('shows no helper text under the token and template fields', async () => {
    const wrapper = mountSection()
    await flushPromises()

    expect(wrapper.text()).not.toContain('Leave empty to keep the current token')
    expect(wrapper.text()).not.toContain('A missing field stays empty')
  })

  it('lists every job field as a template variable', async () => {
    const wrapper = mountSection()
    await flushPromises()

    const chips = wrapper.findAll('[data-slot="template-variable"]').map((chip) => chip.text())
    expect(chips).toEqual(['{title}', '{company}', '{url}'])
  })

  it('inserts a variable at the cursor in the template', async () => {
    const wrapper = mountSection()
    await flushPromises()
    const template = wrapper.get('#discord-template')
    await template.setValue('New  job')
    const element = template.element as HTMLTextAreaElement
    element.setSelectionRange(4, 4)

    await wrapper.findAll('[data-slot="template-variable"]')[0]!.trigger('click')

    expect(element.value).toBe('New {title} job')
  })

  it('finds the template field without looking it up in the document', async () => {
    const wrapper = mountSection(createPinia(), false)
    await flushPromises()
    const template = wrapper.get('#discord-template')
    await template.setValue('New  job')
    const element = template.element as HTMLTextAreaElement
    element.setSelectionRange(4, 4)

    await chips(wrapper)[0]!.trigger('click')

    expect(element.value).toBe('New {title} job')
  })

  it('inserts a variable at the end when the caret is at the end', async () => {
    const wrapper = mountSection()
    await flushPromises()
    const template = wrapper.get('#discord-template')
    await template.setValue('New job ')
    const element = template.element as HTMLTextAreaElement
    element.setSelectionRange(8, 8)

    await chips(wrapper)[1]!.trigger('click')

    expect(element.value).toBe('New job {company}')
  })

  it('names each variable chip and ties the chips to the template field', async () => {
    const wrapper = mountSection()
    await flushPromises()

    const group = wrapper.get('[role="group"]')
    expect(wrapper.get('#discord-template').attributes('aria-describedby')).toBe(
      group.attributes('id'),
    )
    expect(group.attributes('aria-label')).toBe('Template variables')
    expect(chips(wrapper).map((chip) => chip.attributes('aria-label'))).toEqual([
      'Insert title',
      'Insert company',
      'Insert url',
    ])
    expect(chips(wrapper)[0]!.attributes('aria-controls')).toBe('discord-template')
  })

  it('loads the config again once when it had failed so the variables show', async () => {
    getConfig.execute.mockRejectedValueOnce(new Error('down'))
    const pinia = createPinia()
    setActivePinia(pinia)
    await useConfigStore().load()

    const wrapper = mountSection(pinia)
    await flushPromises()

    expect(getConfig.execute).toHaveBeenCalledTimes(2)
    expect(chips(wrapper)).toHaveLength(3)
  })

  it('tries the failed config load only once per mount', async () => {
    getConfig.execute.mockRejectedValue(new Error('down'))
    const pinia = createPinia()
    setActivePinia(pinia)
    await useConfigStore().load()

    const wrapper = mountSection(pinia)
    await flushPromises()

    expect(getConfig.execute).toHaveBeenCalledTimes(2)
    expect(chips(wrapper)).toHaveLength(0)
  })

  it('never shows the token and uses the hint as the placeholder', async () => {
    const wrapper = mountSection()
    await flushPromises()

    expect(inputValue(wrapper, '#discord-token')).toBe('')
    expect(wrapper.get('#discord-token').attributes('placeholder')).toBe('••••1234')
  })

  it('asks for a token when none is saved', async () => {
    getSettings.execute.mockResolvedValue({ ...SETTINGS, isConfigured: false, tokenHint: null })
    const wrapper = mountSection()
    await flushPromises()

    expect(wrapper.get('#discord-token').attributes('placeholder')).toBe('Bot token')
  })

  it('leaves the token out of the save when its box is empty', async () => {
    saveSettings.execute.mockResolvedValue(SETTINGS)
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.get('#discord-template').setValue('{title}')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveSettings.execute).toHaveBeenCalledTimes(1)
    const changes = saveSettings.execute.mock.calls[0]![0]
    expect(changes).not.toHaveProperty('token')
    expect(changes).toEqual({ messageTemplate: '{title}' })
  })

  it('sends only the token on a first save so the defaults stay out of the database', async () => {
    saveSettings.execute.mockResolvedValue(SETTINGS)
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.get('#discord-token').setValue('new.token')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveSettings.execute.mock.calls[0]![0]).toEqual({ token: 'new.token' })
  })

  it('sends a typed token', async () => {
    saveSettings.execute.mockResolvedValue(SETTINGS)
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('#discord-token').setValue('new.token')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveSettings.execute.mock.calls[0]![0].token).toBe('new.token')
  })

  it('sends null for a cleared channel and user id', async () => {
    saveSettings.execute.mockResolvedValue(SETTINGS)
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('#discord-default-channel').setValue('')
    await wrapper.get('#discord-mention-user').setValue('')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const changes = saveSettings.execute.mock.calls[0]![0]
    expect(changes.defaultChannelId).toBeNull()
    expect(changes.mentionUserId).toBeNull()
  })

  it('empties the token box and says saved after a save', async () => {
    saveSettings.execute.mockResolvedValue({ ...SETTINGS, tokenHint: '••••9999' })
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.get('#discord-token').setValue('new.token')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(inputValue(wrapper, '#discord-token')).toBe('')
    expect(wrapper.get('#discord-token').attributes('placeholder')).toBe('••••9999')
    expect(toastSuccess).toHaveBeenCalledWith('Discord settings saved')
  })

  it('shows the message when a save fails and keeps what was typed', async () => {
    saveSettings.execute.mockRejectedValue(new Error('Invalid channel id'))
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.get('#discord-token').setValue('new.token')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Invalid channel id')
    expect(inputValue(wrapper, '#discord-token')).toBe('new.token')
    expect(toastSuccess).not.toHaveBeenCalled()
  })

  it('turns Save into Saving and off while a save runs', async () => {
    const pending = deferred<DiscordSettings>()
    saveSettings.execute.mockReturnValue(pending.promise)
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.get('#discord-template').setValue('{title}')

    expect(button(wrapper, 'Save').attributes('disabled')).toBeUndefined()

    await wrapper.get('form').trigger('submit')

    expect(button(wrapper, 'Saving').attributes('disabled')).toBeDefined()

    pending.resolve({ ...SETTINGS, messageTemplate: '{title}' })
    await flushPromises()

    expect(button(wrapper, 'Save').exists()).toBe(true)
    expect(wrapper.findAll('button').some((node) => node.text() === 'Saving')).toBe(false)
  })

  it('keeps Save off until the form differs from the saved settings', async () => {
    const wrapper = mountSection()
    await flushPromises()

    expect(isSaveDisabled(wrapper)).toBe(true)
  })

  it.each([
    ['#discord-token', 'new.token', ''],
    ['#discord-default-channel', '22345678901234567', '12345678901234567'],
    ['#discord-mention-user', '', '76543210987654321'],
    ['#discord-max-chars', '1500', '1900'],
    ['#discord-template', '{title}', '{title} at {company}'],
  ])('turns Save on after %s changes and off after it is put back', async (id, typed, saved) => {
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get(id).setValue(typed)

    expect(isSaveDisabled(wrapper)).toBe(false)

    await wrapper.get(id).setValue(saved)

    expect(isSaveDisabled(wrapper)).toBe(true)
  })

  it('keeps Save off when the token box only has spaces', async () => {
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('#discord-token').setValue('   ')

    expect(isSaveDisabled(wrapper)).toBe(true)
  })

  it('turns Save off again after a save', async () => {
    saveSettings.execute.mockResolvedValue({ ...SETTINGS, messageTemplate: '{title}' })
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.get('#discord-template').setValue('{title}')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveSettings.execute).toHaveBeenCalledTimes(1)
    expect(inputValue(wrapper, '#discord-template')).toBe('{title}')
    expect(isSaveDisabled(wrapper)).toBe(true)
  })

  it('keeps Save on after a save fails', async () => {
    saveSettings.execute.mockRejectedValue(new Error('Invalid channel id'))
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.get('#discord-template').setValue('{title}')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(isSaveDisabled(wrapper)).toBe(false)
  })

  it('does not save when the unchanged form is submitted', async () => {
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveSettings.execute).not.toHaveBeenCalled()
    expect(toastSuccess).not.toHaveBeenCalled()
  })

  it('makes the template field taller than the default and keeps it resizable', async () => {
    const wrapper = mountSection()
    await flushPromises()

    const classes = wrapper.get('#discord-template').classes()
    expect(classes).toContain('min-h-64')
    expect(classes).not.toContain('min-h-24')
    expect(classes).toContain('resize-y')
  })

  it('puts the template and its variables left of the preview on wide screens', async () => {
    const wrapper = mountSection()
    await flushPromises()

    const row = wrapper.get('[data-slot="template-row"]')
    expect(row.classes()).toContain('lg:grid-cols-2')
    expect(row.classes()).toContain('items-start')
    const columns = row.element.children
    expect(columns).toHaveLength(2)
    expect(columns[0]!.querySelector('#discord-template')).not.toBeNull()
    expect(columns[0]!.querySelectorAll('[data-slot="template-variable"]')).toHaveLength(3)
    expect(columns[1]!.getAttribute('data-slot')).toBe('template-preview')
    expect(wrapper.get('[data-slot="template-preview-panel"]').classes()).toContain('min-h-64')
  })

  it('previews the saved template filled with the sample job', async () => {
    const wrapper = mountSection()
    await flushPromises()

    expect(previewHtml(wrapper).text()).toBe(
      'IoT Solution Engineer (Fullstack IoT) at PT Onesia Nusantara Evolusioner',
    )
  })

  it('previews the template as formatted markdown with safe links', async () => {
    const wrapper = mountSection()
    await flushPromises()

    await wrapper
      .get('#discord-template')
      .setValue('## {title}\n**{company}**\n{location}\n[Apply]({url})\n{requirements}')
    await flushPromises()

    const preview = previewHtml(wrapper)
    expect(preview.get('h2').text()).toBe('IoT Solution Engineer (Fullstack IoT)')
    expect(preview.get('strong').text()).toBe('PT Onesia Nusantara Evolusioner')
    expect(preview.findAll('br').length).toBeGreaterThan(0)
    expect(preview.findAll('li')).toHaveLength(5)
    const link = preview.get('a')
    expect(link.text()).toBe('Apply')
    expect(link.attributes('href')).toBe('https://id.jobstreet.com/id/job/00000000')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toBe('noopener noreferrer')
  })

  it('updates the preview while the template is typed', async () => {
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('#discord-template').setValue('Hiring: {title} ({nope})')
    await flushPromises()

    expect(previewHtml(wrapper).text()).toBe('Hiring: IoT Solution Engineer (Fullstack IoT) (-)')
  })

  it('updates the preview after a variable chip is clicked', async () => {
    const wrapper = mountSection()
    await flushPromises()
    const template = wrapper.get('#discord-template')
    await template.setValue('At ')
    const element = template.element as HTMLTextAreaElement
    element.setSelectionRange(3, 3)

    await chips(wrapper)[1]!.trigger('click')
    await flushPromises()

    expect(element.value).toBe('At {company}')
    expect(document.activeElement).toBe(element)
    expect(previewHtml(wrapper).text()).toBe('At PT Onesia Nusantara Evolusioner')
  })

  it('never cuts the preview at the max characters field', async () => {
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('#discord-max-chars').setValue('12')
    await flushPromises()

    expect(previewHtml(wrapper).text()).toBe(
      'IoT Solution Engineer (Fullstack IoT) at PT Onesia Nusantara Evolusioner',
    )
  })

  it('explains that job digests skip the max characters field', async () => {
    const wrapper = mountSection()
    await flushPromises()

    const input = wrapper.get('#discord-max-chars')
    const hint = wrapper.get(`[id="${input.attributes('aria-describedby')}"]`)
    expect(hint.text()).toBe(
      'Job digests skip this limit, every job goes in full into the attached file',
    )
  })

  it('shows a hint instead of an empty preview for an empty template', async () => {
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('#discord-template').setValue('')
    await flushPromises()

    expect(wrapper.find('[data-slot="template-preview-html"]').exists()).toBe(false)
    expect(wrapper.get('[data-slot="template-preview-empty"]').text()).toBe(
      'Write a template to see the preview',
    )
  })

  it('labels the preview and does not announce it while typing', async () => {
    const wrapper = mountSection()
    await flushPromises()

    const preview = wrapper.get('[data-slot="template-preview"]')
    const label = wrapper.get(`[id="${preview.attributes('aria-labelledby')}"]`)
    const caption = wrapper.get(`[id="${preview.attributes('aria-describedby')}"]`)
    expect(label.text()).toBe('Preview')
    expect(caption.text()).toBe(
      'Filled with a sample job, each job in the digest file looks like this',
    )
    expect(preview.find('[aria-live]').exists()).toBe(false)
    expect(preview.find('[role="status"]').exists()).toBe(false)
    expect(preview.find('input, textarea, [contenteditable]').exists()).toBe(false)
  })

  it('tests the connection and shows the bot name', async () => {
    testConnection.execute.mockResolvedValue({ name: 'Jobs bot', id: '42' })
    const wrapper = mountSection()
    await flushPromises()

    await button(wrapper, 'Test connection').trigger('click')
    await flushPromises()

    expect(testConnection.execute).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[role="status"]').text()).toContain('Jobs bot')
    expect(saveSettings.execute).not.toHaveBeenCalled()
  })

  it('shows the message when the test fails', async () => {
    testConnection.execute.mockRejectedValue(new Error('Discord rejected the bot token.'))
    const wrapper = mountSection()
    await flushPromises()

    await button(wrapper, 'Test connection').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Discord rejected the bot token.')
  })

  it('turns the test button into Testing and off while it runs', async () => {
    const pending = deferred<{ name: string; id: string }>()
    testConnection.execute.mockReturnValue(pending.promise)
    const wrapper = mountSection()
    await flushPromises()

    await button(wrapper, 'Test connection').trigger('click')

    expect(button(wrapper, 'Testing').attributes('disabled')).toBeDefined()

    pending.resolve({ name: 'Jobs bot', id: '42' })
    await flushPromises()
  })

  it('puts Send last result before Test connection and Save in the button row', async () => {
    const wrapper = mountSection()
    await flushPromises()

    const row = button(wrapper, 'Save').element.parentElement!
    const labels = [...row.querySelectorAll('button')].map((node) => node.textContent?.trim())
    expect(labels).toEqual(['Send last result', 'Test connection', 'Save'])
    expect(button(wrapper, 'Send last result').attributes('data-variant')).toBe(
      button(wrapper, 'Test connection').attributes('data-variant'),
    )
    expect(button(wrapper, 'Save').attributes('data-variant')).toBe('primary')
  })

  it('sends the last result without saving or changing the form', async () => {
    sendLatestScrapeToDiscord.execute.mockResolvedValue({
      ...LATEST_SCRAPE.record,
      discordStatus: 'sending',
    })
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.get('#discord-template').setValue('{title} only')

    await button(wrapper, 'Send last result').trigger('click')
    await flushPromises()

    expect(sendLatestScrapeToDiscord.execute).toHaveBeenCalledTimes(1)
    expect(saveSettings.execute).not.toHaveBeenCalled()
    expect(inputValue(wrapper, '#discord-template')).toBe('{title} only')
    expect(inputValue(wrapper, '#discord-max-chars')).toBe('1900')
    expect(isSaveDisabled(wrapper)).toBe(false)
    expect(button(wrapper, 'Sending').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[role="status"]').text()).toBe('Sending the last result to Discord')
    wrapper.unmount()
  })

  it('keeps Send last result on while the form is unchanged and Save is off', async () => {
    const wrapper = mountSection()
    await flushPromises()

    expect(isSaveDisabled(wrapper)).toBe(true)
    expect(button(wrapper, 'Send last result').attributes('disabled')).toBeUndefined()
  })

  it('keeps Send last result off when the saved settings have no default channel', async () => {
    getSettings.execute.mockResolvedValue({ ...SETTINGS, defaultChannelId: null })
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.get('#discord-default-channel').setValue('12345678901234567')

    expect(button(wrapper, 'Send last result').attributes('disabled')).toBeDefined()
  })

  it('keeps the test button off when no token is saved', async () => {
    getSettings.execute.mockResolvedValue({ ...SETTINGS, isConfigured: false, tokenHint: null })
    const wrapper = mountSection()
    await flushPromises()

    expect(button(wrapper, 'Test connection').attributes('disabled')).toBeDefined()
  })
})

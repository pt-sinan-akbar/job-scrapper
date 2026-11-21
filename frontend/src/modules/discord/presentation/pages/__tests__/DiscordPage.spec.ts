import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import type { DiscordChannel, DiscordSettings } from '@/modules/discord/domain/entities/Discord'
import DiscordPage from '@/modules/discord/presentation/pages/DiscordPage.vue'
import { provideDiscordUseCases } from '@/modules/discord/presentation/stores/discordUseCases'
import { useDiscordSettingsStore } from '@/modules/discord/presentation/stores/useDiscordSettingsStore'

const toast = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }))

vi.mock('vue-sonner', () => ({ toast }))

const getSettings = { execute: vi.fn() }
const saveSettings = { execute: vi.fn() }
const testConnection = { execute: vi.fn() }
const listChannels = { execute: vi.fn() }
const previewMessage = { execute: vi.fn() }
const sendMessage = { execute: vi.fn() }

const CHANNEL_ID = '12345678901234567'
const USER_ID = '76543210987654321'
const PREFIX_LENGTH = `<@${USER_ID}>\n`.length

const SETTINGS: DiscordSettings = {
  isConfigured: true,
  tokenHint: '••••1234',
  defaultChannelId: CHANNEL_ID,
  mentionUserId: USER_ID,
  messageTemplate: '{title}',
  maxChars: 1900,
  updatedAt: null,
}

const CHANNELS: DiscordChannel[] = [
  { id: CHANNEL_ID, name: 'jobs', guildId: '1', guildName: 'Home' },
]

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve: (value: T) => void = () => undefined
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

async function mountPage(pinia: Pinia = createPinia()) {
  const wrapper = mount(DiscordPage, {
    global: { plugins: [pinia] },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

type Wrapper = Awaited<ReturnType<typeof mountPage>>

function button(wrapper: Wrapper, label: string) {
  return wrapper.findAll('button').find((node) => node.text() === label)!
}

describe('DiscordPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    getSettings.execute.mockResolvedValue(SETTINGS)
    listChannels.execute.mockResolvedValue(CHANNELS)
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

  it('shows the page skeleton until the settings load', async () => {
    const first = deferred<DiscordSettings>()
    getSettings.execute.mockReturnValue(first.promise)
    const wrapper = await mountPage()

    expect(wrapper.find('[data-slot="page-skeleton"]').exists()).toBe(true)
    expect(wrapper.find('form').exists()).toBe(false)

    first.resolve(SETTINGS)
    await flushPromises()

    expect(wrapper.find('[data-slot="page-skeleton"]').exists()).toBe(false)
    expect(wrapper.find('form').exists()).toBe(true)
  })

  it('shows an error with a retry when the settings fail', async () => {
    getSettings.execute.mockRejectedValueOnce(new Error('Scraper down'))
    const wrapper = await mountPage()

    expect(wrapper.get('[role="alert"]').text()).toContain('Scraper down')

    await button(wrapper, 'Try again').trigger('click')
    await flushPromises()

    expect(wrapper.find('form').exists()).toBe(true)
  })

  it('shows only the bot settings and a hint when the bot is not set up', async () => {
    getSettings.execute.mockResolvedValue({ ...SETTINGS, isConfigured: false, tokenHint: null })
    const wrapper = await mountPage()

    expect(wrapper.text()).toContain('Save a bot token below to start sending messages')
    expect(wrapper.find('#discord-token').exists()).toBe(true)
    expect(wrapper.find('#discord-channel').exists()).toBe(false)
    expect(listChannels.execute).not.toHaveBeenCalled()
  })

  it('shows the send form right after the first bot settings save', async () => {
    getSettings.execute.mockResolvedValue({ ...SETTINGS, isConfigured: false, tokenHint: null })
    saveSettings.execute.mockResolvedValue(SETTINGS)
    const wrapper = await mountPage()

    await wrapper.get('#discord-token').setValue('new-token')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(listChannels.execute).toHaveBeenCalledTimes(1)
    expect(wrapper.find('#discord-channel').exists()).toBe(true)
  })

  it('puts the bot settings below the send form', async () => {
    const wrapper = await mountPage()

    const forms = wrapper.findAll('form')
    expect(forms).toHaveLength(2)
    expect(forms[0]!.find('#discord-channel').exists()).toBe(true)
    expect(forms[1]!.find('#discord-token').exists()).toBe(true)
    expect(wrapper.text()).toContain('Bot settings')
  })

  it('reloads the channels when the bot settings are saved again', async () => {
    saveSettings.execute.mockResolvedValue({ ...SETTINGS, mentionUserId: null })
    const wrapper = await mountPage()
    await wrapper.get('#discord-mention-user').setValue('')

    await wrapper.findAll('form')[1]!.trigger('submit')
    await flushPromises()

    expect(listChannels.execute).toHaveBeenCalledTimes(2)
    expect(wrapper.find('#discord-mention').exists()).toBe(false)
  })

  it('loads the settings once on mount', async () => {
    await mountPage()

    expect(getSettings.execute).toHaveBeenCalledTimes(1)
  })

  it('does not load the settings or channels twice when the settings are already loaded', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    await useDiscordSettingsStore().load()

    await mountPage(pinia)

    expect(getSettings.execute).toHaveBeenCalledTimes(1)
    expect(listChannels.execute).toHaveBeenCalledTimes(1)
  })

  it('keeps the compose choices when the page mounts again', async () => {
    const pinia = createPinia()
    const wrapper = await mountPage(pinia)
    await wrapper.get('#discord-mention').trigger('click')
    wrapper.unmount()

    const again = await mountPage(pinia)

    expect(getSettings.execute).toHaveBeenCalledTimes(1)
    expect(listChannels.execute).toHaveBeenCalledTimes(1)
    expect(again.get('#discord-mention').attributes('data-state')).toBe('unchecked')
  })

  it('shows an error with a retry when the channels fail', async () => {
    listChannels.execute.mockRejectedValueOnce(new Error('Discord rejected the bot token.'))
    const wrapper = await mountPage()

    expect(wrapper.get('[role="alert"]').text()).toContain('Discord rejected the bot token.')

    await button(wrapper, 'Try again').trigger('click')
    await flushPromises()

    expect(wrapper.find('form').exists()).toBe(true)
  })

  it('preselects the default channel', async () => {
    const wrapper = await mountPage()

    expect(wrapper.get('#discord-channel').text()).toContain('jobs')
  })

  it('renders the free text compose only', async () => {
    const wrapper = await mountPage()

    expect(wrapper.find('#discord-text').exists()).toBe(true)
    expect(wrapper.findAll('[role="tab"]')).toHaveLength(0)
    expect(wrapper.find('#discord-run').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Scraper result')
    expect(button(wrapper, 'Send').attributes('disabled')).toBeDefined()
  })

  it('puts the whole compose in one card with Message and Preview side by side', async () => {
    const wrapper = await mountPage()

    const card = wrapper.get('[data-slot="compose-card"]')
    expect(card.find('#discord-channel').exists()).toBe(true)
    expect(card.find('#discord-text').exists()).toBe(true)
    expect(card.findAll('button').some((node) => node.text() === 'Send')).toBe(true)
    expect(card.findAll('h3').map((heading) => heading.text())).toEqual(['Send a message'])
    const grid = card.get('[data-slot="compose-grid"]')
    expect(grid.classes()).toContain('md:grid-cols-2')
    expect(grid.text()).toContain('Message')
    expect(grid.text()).toContain('Preview')
  })

  it('says it is loading the channels while they load', async () => {
    listChannels.execute.mockReturnValue(deferred<DiscordChannel[]>().promise)
    const wrapper = await mountPage()

    expect(wrapper.text()).toContain('Loading channels')
    expect(wrapper.text()).not.toContain('runs')
  })

  it('shows the Mention user box ticked only when a user id is saved', async () => {
    const wrapper = await mountPage()
    expect(wrapper.get('#discord-mention').attributes('data-state')).toBe('checked')
    wrapper.unmount()

    getSettings.execute.mockResolvedValue({ ...SETTINGS, mentionUserId: null })
    const without = await mountPage()
    expect(without.find('#discord-mention').exists()).toBe(false)
  })

  it('counts the chars against 2000 including the mention prefix', async () => {
    const wrapper = await mountPage()

    await wrapper.get('#discord-text').setValue('hello')

    expect(wrapper.get('#discord-char-count').text()).toBe(`${PREFIX_LENGTH + 5} / 2000`)

    await wrapper.get('#discord-mention').trigger('click')

    expect(wrapper.get('#discord-char-count').text()).toBe('5 / 2000')
  })

  it('links the counter to the textarea and announces it politely', async () => {
    const wrapper = await mountPage()

    expect(wrapper.get('#discord-text').attributes('aria-describedby')).toBe('discord-char-count')
    expect(wrapper.get('#discord-char-count').attributes('aria-live')).toBe('polite')
  })

  it('turns the counter into a warning and Send off past 2000 chars', async () => {
    const wrapper = await mountPage()

    await wrapper.get('#discord-text').setValue('a'.repeat(2000))

    expect(wrapper.get('#discord-char-count').attributes('data-over')).toBe('true')
    expect(button(wrapper, 'Send').attributes('disabled')).toBeDefined()
  })

  it('previews free text and shows every message', async () => {
    previewMessage.execute.mockResolvedValue(['first message', 'second message'])
    const wrapper = await mountPage()
    await wrapper.get('#discord-text').setValue('hello')

    await button(wrapper, 'Preview').trigger('click')
    await flushPromises()

    expect(previewMessage.execute).toHaveBeenCalledWith(true, { text: 'hello' })
    const messages = wrapper.findAll('[data-slot="discord-preview-message"]')
    expect(messages.map((node) => node.text())).toEqual(['first message', 'second message'])
  })

  it('shows the message when the preview fails', async () => {
    previewMessage.execute.mockRejectedValue(new Error('Text is too long'))
    const wrapper = await mountPage()
    await wrapper.get('#discord-text').setValue('hello')

    await button(wrapper, 'Preview').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Text is too long')
  })

  it('sends free text, shows a success toast and lists the results', async () => {
    sendMessage.execute.mockResolvedValue({
      sent: 1,
      failed: 0,
      results: [
        {
          index: 0,
          kind: 'text',
          title: null,
          jobCount: 0,
          status: 'sent',
          messageId: '1',
          error: null,
        },
      ],
    })
    const wrapper = await mountPage()
    await wrapper.get('#discord-text').setValue('hello')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(sendMessage.execute).toHaveBeenCalledWith(CHANNEL_ID, true, { text: 'hello' })
    expect(toast.success).toHaveBeenCalledWith('Sent 1 message')
    expect(wrapper.findAll('[data-slot="discord-send-results"] li')).toHaveLength(1)
  })

  it('shows a warning toast when some messages fail', async () => {
    sendMessage.execute.mockResolvedValue({ sent: 1, failed: 1, results: [] })
    const wrapper = await mountPage()
    await wrapper.get('#discord-text').setValue('hello')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(toast.warning).toHaveBeenCalledWith('Sent 1, 1 failed')
  })

  it('shows an error toast when every message fails', async () => {
    sendMessage.execute.mockResolvedValue({ sent: 0, failed: 2, results: [] })
    const wrapper = await mountPage()
    await wrapper.get('#discord-text').setValue('hello')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(toast.error).toHaveBeenCalledWith('Nothing was sent, 2 failed')
  })

  it('shows the message inline and in a toast when the send is refused', async () => {
    sendMessage.execute.mockRejectedValue(new Error("The bot can't post in that channel."))
    const wrapper = await mountPage()
    await wrapper.get('#discord-text').setValue('hello')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain("The bot can't post in that channel.")
    expect(toast.error).toHaveBeenCalledWith("The bot can't post in that channel.")
  })

  it('turns Send into Sending and off while it runs', async () => {
    const pending = deferred<{ sent: number; failed: number; results: never[] }>()
    sendMessage.execute.mockReturnValue(pending.promise)
    const wrapper = await mountPage()
    await wrapper.get('#discord-text').setValue('hello')

    await wrapper.get('form').trigger('submit')

    expect(button(wrapper, 'Sending').attributes('disabled')).toBeDefined()

    pending.resolve({ sent: 1, failed: 0, results: [] })
    await flushPromises()
  })
})

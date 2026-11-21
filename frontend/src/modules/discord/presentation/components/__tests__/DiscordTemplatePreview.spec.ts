import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import DiscordTemplatePreview from '@/modules/discord/presentation/components/DiscordTemplatePreview.vue'
import type { MarkdownRenderOptions } from '@/shared/utils/markdown'

const renderMarkdownMock = vi.hoisted(() =>
  vi.fn<(markdown: string, options?: MarkdownRenderOptions) => Promise<string>>(),
)

vi.mock('@/shared/utils/markdown', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/shared/utils/markdown')>()
  return { ...actual, renderMarkdown: renderMarkdownMock }
})

const TITLE = 'IoT Solution Engineer (Fullstack IoT)'
const COMPANY = 'PT Onesia Nusantara Evolusioner'

interface Deferred {
  promise: Promise<string>
  resolve: (html: string) => void
  reject: (error: Error) => void
}

function defer(): Deferred {
  let settle: (html: string) => void = () => undefined
  let fail: (error: Error) => void = () => undefined
  const promise = new Promise<string>((resolve, reject) => {
    settle = resolve
    fail = reject
  })
  return { promise, resolve: (html) => settle(html), reject: (error) => fail(error) }
}

function toParagraph(markdown: string): Promise<string> {
  return Promise.resolve(`<p>${markdown}</p>`)
}

function mountPreview(messageTemplate = '{title}', errorHandler = vi.fn()) {
  const wrapper = mount(DiscordTemplatePreview, {
    props: { messageTemplate },
    global: { config: { errorHandler } },
  })
  return { wrapper, errorHandler }
}

type Wrapper = ReturnType<typeof mountPreview>['wrapper']

function html(wrapper: Wrapper) {
  return wrapper.find('[data-slot="template-preview-html"]')
}

function plainText(wrapper: Wrapper) {
  return wrapper.find('[data-slot="template-preview-text"]')
}

function emptyHint(wrapper: Wrapper) {
  return wrapper.find('[data-slot="template-preview-empty"]')
}

function errorNote(wrapper: Wrapper) {
  return wrapper.find('[data-slot="template-preview-error"]')
}

describe('DiscordTemplatePreview', () => {
  beforeEach(() => {
    renderMarkdownMock.mockReset()
    renderMarkdownMock.mockImplementation(toParagraph)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the template filled with the sample job and keeps single line breaks', async () => {
    const { wrapper } = mountPreview('{title}\n{company}')
    await flushPromises()

    expect(renderMarkdownMock).toHaveBeenCalledTimes(1)
    expect(renderMarkdownMock).toHaveBeenCalledWith(`${TITLE}\n${COMPANY}`, {
      shouldKeepLineBreaks: true,
    })
    expect(html(wrapper).element.innerHTML).toBe(`<p>${TITLE}\n${COMPANY}</p>`)
  })

  it('renders again when the template changes', async () => {
    const { wrapper } = mountPreview('{title}')
    await flushPromises()

    await wrapper.setProps({ messageTemplate: '{company}' })
    await flushPromises()

    expect(html(wrapper).text()).toBe(COMPANY)
  })

  it('shows a long filled job in full without cutting it', async () => {
    const longTemplate = '{title} '.repeat(80)
    const { wrapper } = mountPreview(longTemplate)
    await flushPromises()

    expect(html(wrapper).text()).toBe(`${TITLE} `.repeat(80).trim())
  })

  it('shows the filled text as plain text while the first render is pending', async () => {
    const pending = defer()
    renderMarkdownMock.mockReturnValue(pending.promise)
    const { wrapper } = mountPreview('**{title}**\nsecond line')
    await flushPromises()

    expect(html(wrapper).exists()).toBe(false)
    expect(plainText(wrapper).element.textContent?.trim()).toBe(`**${TITLE}**\nsecond line`)
    expect(plainText(wrapper).classes()).toContain('whitespace-pre-wrap')
    expect(plainText(wrapper).attributes('aria-busy')).toBe('true')
    expect(errorNote(wrapper).exists()).toBe(false)

    pending.resolve('<p>Rendered</p>')
    await flushPromises()

    expect(html(wrapper).text()).toBe('Rendered')
    expect(plainText(wrapper).exists()).toBe(false)
  })

  it('keeps the last preview on screen while a newer render is pending', async () => {
    const { wrapper } = mountPreview('{title}')
    await flushPromises()
    const pending = defer()
    renderMarkdownMock.mockReturnValue(pending.promise)

    await wrapper.setProps({ messageTemplate: '{company}' })
    await flushPromises()

    expect(html(wrapper).text()).toBe(TITLE)

    pending.resolve('<p>Newer</p>')
    await flushPromises()

    expect(html(wrapper).text()).toBe('Newer')
  })

  it('ignores an older render that finishes after a newer one', async () => {
    const older = defer()
    const newer = defer()
    renderMarkdownMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise)
    const { wrapper } = mountPreview('{title}')

    await wrapper.setProps({ messageTemplate: '{company}' })
    newer.resolve('<p>Newer</p>')
    await flushPromises()
    older.resolve('<p>Stale</p>')
    await flushPromises()

    expect(renderMarkdownMock).toHaveBeenCalledTimes(2)
    expect(html(wrapper).text()).toBe('Newer')
    expect(wrapper.text()).not.toContain('Stale')
  })

  it('ignores an older render that fails after a newer one worked', async () => {
    const older = defer()
    const newer = defer()
    renderMarkdownMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise)
    const { wrapper, errorHandler } = mountPreview('{title}')

    await wrapper.setProps({ messageTemplate: '{company}' })
    newer.resolve('<p>Newer</p>')
    await flushPromises()
    older.reject(new Error('offline'))
    await flushPromises()

    expect(html(wrapper).text()).toBe('Newer')
    expect(errorNote(wrapper).exists()).toBe(false)
    expect(errorHandler).toHaveBeenCalledTimes(1)
  })

  it('shows the filled text as plain text with a note when rendering fails', async () => {
    const failure = new Error('chunk failed to load')
    renderMarkdownMock.mockRejectedValue(failure)
    const { wrapper, errorHandler } = mountPreview('**{title}**\nsecond line')
    await flushPromises()

    expect(html(wrapper).exists()).toBe(false)
    expect(plainText(wrapper).element.textContent?.trim()).toBe(`**${TITLE}**\nsecond line`)
    expect(plainText(wrapper).attributes('aria-busy')).toBeUndefined()
    expect(errorNote(wrapper).text()).toBe('Could not format the preview, showing plain text')
    expect(errorNote(wrapper).attributes('role')).toBe('status')
    expect(errorHandler).toHaveBeenCalledTimes(1)
    expect(errorHandler.mock.calls[0]?.[0]).toBe(failure)
  })

  it('formats the preview again on the next change after a failure', async () => {
    renderMarkdownMock.mockRejectedValueOnce(new Error('offline'))
    const { wrapper } = mountPreview('{title}')
    await flushPromises()

    await wrapper.setProps({ messageTemplate: '{company}' })
    await flushPromises()

    expect(html(wrapper).text()).toBe(COMPANY)
    expect(errorNote(wrapper).exists()).toBe(false)
  })

  it('shows a hint and renders nothing for an empty template', async () => {
    const { wrapper } = mountPreview('  \n ')
    await flushPromises()

    expect(emptyHint(wrapper).text()).toBe('Write a template to see the preview')
    expect(html(wrapper).exists()).toBe(false)
    expect(plainText(wrapper).exists()).toBe(false)
    expect(renderMarkdownMock).not.toHaveBeenCalled()
  })

  it('renders a dash when the template only uses unknown fields', async () => {
    mountPreview('{nope}')
    await flushPromises()

    expect(renderMarkdownMock).toHaveBeenCalledWith('-', { shouldKeepLineBreaks: true })
  })

  it('drops the old preview when the template is emptied and filled again', async () => {
    const { wrapper } = mountPreview('{title}')
    await flushPromises()
    await wrapper.setProps({ messageTemplate: '' })
    const pending = defer()
    renderMarkdownMock.mockReturnValue(pending.promise)

    await wrapper.setProps({ messageTemplate: '{company}' })
    await flushPromises()

    expect(html(wrapper).exists()).toBe(false)
    expect(plainText(wrapper).text()).toBe(COMPANY)
  })

  it('ignores a render that finishes after the template was emptied', async () => {
    const pending = defer()
    renderMarkdownMock.mockReturnValue(pending.promise)
    const { wrapper } = mountPreview('{title}')

    await wrapper.setProps({ messageTemplate: '' })
    pending.resolve('<p>Stale</p>')
    await flushPromises()

    expect(emptyHint(wrapper).exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Stale')
  })

  it('labels the preview region and stays quiet for screen readers', async () => {
    const { wrapper } = mountPreview()
    await flushPromises()

    const labelId = wrapper.attributes('aria-labelledby')
    const captionId = wrapper.attributes('aria-describedby')
    expect(wrapper.element.tagName).toBe('SECTION')
    expect(wrapper.get(`[id="${labelId}"]`).text()).toBe('Preview')
    expect(wrapper.get(`[id="${captionId}"]`).text()).toBe(
      'Filled with a sample job, each job in the digest file looks like this',
    )
    expect(wrapper.find('[aria-live]').exists()).toBe(false)
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('wraps long words in the panel and in the plain text', async () => {
    const pending = defer()
    renderMarkdownMock.mockReturnValue(pending.promise)
    const { wrapper } = mountPreview('{url}')
    await flushPromises()

    expect(wrapper.get('[data-slot="template-preview-panel"]').classes()).toContain('min-w-0')
    expect(plainText(wrapper).classes()).toContain('wrap-anywhere')
  })
})

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { stubClampedText } from '@/__tests__/clampedText'
import { nextTick } from 'vue'
import RunJobDescription from '@/modules/runs/presentation/components/RunJobDescription.vue'

const renderMarkdownMock = vi.hoisted(() => vi.fn<(markdown: string) => Promise<string>>())

vi.mock('@/shared/utils/markdown', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/shared/utils/markdown')>()
  return { ...actual, renderMarkdown: renderMarkdownMock }
})

const DESCRIPTION = [
  '## About the role',
  '',
  'We are looking for a **senior engineer** who enjoys shipping reliable data pipelines.',
  '',
  '- Design scraping jobs that survive layout changes',
  '- Keep the on call rotation calm and well documented',
].join('\n')
const OTHER_DESCRIPTION = `${DESCRIPTION}\n\nA second paragraph that makes this another description.`
const HTML = '<h2>About the role</h2><p>Rendered</p>'
const PLAIN_START = 'About the role We are looking for a senior engineer'

interface Deferred {
  promise: Promise<string>
  resolve: (html: string) => void
}

function defer(): Deferred {
  let settle: (html: string) => void = () => undefined
  const promise = new Promise<string>((resolve) => {
    settle = resolve
  })
  return { promise, resolve: (html) => settle(html) }
}

function mountDescription(description = DESCRIPTION, errorHandler = vi.fn()) {
  const wrapper = mount(RunJobDescription, {
    props: { description },
    attachTo: document.body,
    global: { config: { errorHandler } },
  })
  return { wrapper, errorHandler }
}

type Wrapper = ReturnType<typeof mountDescription>['wrapper']

function toggle(wrapper: Wrapper) {
  return wrapper.get('[data-slot="job-description-toggle"]')
}

async function clickToggle(wrapper: Wrapper): Promise<void> {
  await nextTick()
  await toggle(wrapper).trigger('click')
}

function text(wrapper: Wrapper) {
  return wrapper.get('[data-slot="job-description-text"]')
}

function html(wrapper: Wrapper) {
  return wrapper.find('[data-slot="job-description-html"]')
}

describe('RunJobDescription', () => {
  beforeEach(() => {
    renderMarkdownMock.mockReset()
    renderMarkdownMock.mockResolvedValue(HTML)
    stubClampedText(true)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('offers no toggle when the whole text fits in the preview', async () => {
    stubClampedText(false)
    const { wrapper } = mountDescription()
    await nextTick()

    expect(wrapper.find('[data-slot="job-description-toggle"]').exists()).toBe(false)
  })

  it('offers the toggle for a short text that still overflows the preview', async () => {
    const { wrapper } = mountDescription('A short note on a narrow card')
    await nextTick()

    expect(toggle(wrapper).text()).toBe('Show more')
  })

  it('offers the toggle once a new description overflows the preview', async () => {
    stubClampedText(false)
    const { wrapper } = mountDescription()
    stubClampedText(true)

    await wrapper.setProps({ description: OTHER_DESCRIPTION })
    await nextTick()

    expect(toggle(wrapper).text()).toBe('Show more')
  })

  it('does not render the markdown until it is expanded', () => {
    const { wrapper } = mountDescription()

    expect(wrapper.attributes('data-slot')).toBe('job-description')
    expect(text(wrapper).text()).toContain(PLAIN_START)
    expect(renderMarkdownMock).not.toHaveBeenCalled()
  })

  it('keeps showing the full plain text while the markdown loads', async () => {
    const pending = defer()
    renderMarkdownMock.mockReturnValue(pending.promise)
    const { wrapper } = mountDescription()

    await clickToggle(wrapper)

    expect(html(wrapper).exists()).toBe(false)
    expect(text(wrapper).text()).toContain(PLAIN_START)
    expect(text(wrapper).classes()).not.toContain('line-clamp-3')
    expect(text(wrapper).attributes('aria-busy')).toBe('true')
    expect(toggle(wrapper).text()).toBe('Show less')

    pending.resolve(HTML)
    await flushPromises()

    expect(html(wrapper).html()).toContain('<p>Rendered</p>')
    expect(wrapper.find('[data-slot="job-description-text"]').exists()).toBe(false)
  })

  it('renders the markdown once and reuses it', async () => {
    const { wrapper } = mountDescription()

    await clickToggle(wrapper)
    await flushPromises()
    await clickToggle(wrapper)
    await clickToggle(wrapper)
    await flushPromises()

    expect(renderMarkdownMock).toHaveBeenCalledTimes(1)
    expect(renderMarkdownMock).toHaveBeenCalledWith(DESCRIPTION)
    expect(html(wrapper).exists()).toBe(true)
  })

  it('shows the full plain text and reports the error when rendering fails', async () => {
    const failure = new Error('chunk failed to load')
    renderMarkdownMock.mockRejectedValue(failure)
    const { wrapper, errorHandler } = mountDescription()

    await clickToggle(wrapper)
    await flushPromises()

    expect(html(wrapper).exists()).toBe(false)
    expect(text(wrapper).text()).toContain(PLAIN_START)
    expect(text(wrapper).text()).toContain('well documented')
    expect(text(wrapper).classes()).not.toContain('line-clamp-3')
    expect(text(wrapper).attributes('aria-busy')).toBeUndefined()
    expect(wrapper.get('[data-slot="job-description-error"]').text()).toBe(
      'Could not format this description, showing plain text',
    )
    expect(toggle(wrapper).text()).toBe('Show less')
    expect(errorHandler).toHaveBeenCalledTimes(1)
    expect(errorHandler.mock.calls[0]?.[0]).toBe(failure)
  })

  it('tries again on the next expand after a failure', async () => {
    renderMarkdownMock.mockRejectedValueOnce(new Error('offline'))
    const { wrapper } = mountDescription()

    await clickToggle(wrapper)
    await flushPromises()
    await clickToggle(wrapper)

    expect(wrapper.find('[data-slot="job-description-error"]').exists()).toBe(false)
    expect(text(wrapper).classes()).toContain('line-clamp-3')

    await clickToggle(wrapper)
    await flushPromises()

    expect(renderMarkdownMock).toHaveBeenCalledTimes(2)
    expect(html(wrapper).html()).toContain('<p>Rendered</p>')
    expect(wrapper.find('[data-slot="job-description-error"]').exists()).toBe(false)
  })

  it('collapses and drops the old markup when the description changes', async () => {
    const { wrapper } = mountDescription()
    await clickToggle(wrapper)
    await flushPromises()

    await wrapper.setProps({ description: OTHER_DESCRIPTION })

    expect(html(wrapper).exists()).toBe(false)
    expect(text(wrapper).text()).toContain('A second paragraph')
    expect(text(wrapper).classes()).toContain('line-clamp-3')
    expect(toggle(wrapper).attributes('aria-expanded')).toBe('false')
  })

  it('ignores markup that arrives for a description that was replaced', async () => {
    const pending = defer()
    renderMarkdownMock.mockReturnValueOnce(pending.promise)
    const { wrapper } = mountDescription()
    await clickToggle(wrapper)

    await wrapper.setProps({ description: OTHER_DESCRIPTION })
    pending.resolve('<p>Stale</p>')
    await flushPromises()
    await clickToggle(wrapper)
    await flushPromises()

    expect(renderMarkdownMock).toHaveBeenLastCalledWith(OTHER_DESCRIPTION)
    expect(html(wrapper).html()).toContain('<p>Rendered</p>')
    expect(html(wrapper).html()).not.toContain('Stale')
  })

  it('renders nothing when the markdown has no text', () => {
    const { wrapper } = mountDescription('---\n\n<br>')

    expect(wrapper.find('[data-slot="job-description"]').exists()).toBe(false)
  })
})

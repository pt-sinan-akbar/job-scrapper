import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { JsonValue } from '@/modules/runs/domain/entities/Run'
import JsonViewer from '@/modules/runs/presentation/components/JsonViewer.vue'
import { MAX_HIGHLIGHT_CHARS, prettyJson } from '@/modules/runs/presentation/components/jsonTokens'

const FEEDBACK_MS = 2000
const COPY_FAILED_MESSAGE = 'Could not copy. Select the text and copy it by hand'

interface ViewerOptions {
  label?: string
  isFullscreenHidden?: boolean
}

function mountViewer(value: JsonValue, options: ViewerOptions = {}) {
  return mount(JsonViewer, { props: { value, ...options }, attachTo: document.body })
}

type Wrapper = ReturnType<typeof mountViewer>

function oversizedValue(): JsonValue {
  return { text: 'x'.repeat(MAX_HIGHLIGHT_CHARS), n: 1, flag: true }
}

function stubClipboard(writeText: (text: string) => Promise<void>) {
  vi.stubGlobal('navigator', { clipboard: { writeText } })
}

function resolvingClipboard() {
  return vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined)
}

function copyButton(wrapper: Wrapper) {
  return wrapper.get('button[data-slot="json-copy"]')
}

function scrollRegion(wrapper: Wrapper) {
  return wrapper.get('[data-slot="json-scroll"]')
}

describe('JsonViewer', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('shows pretty printed json with two space indents', () => {
    const wrapper = mountViewer({ a: { b: 1 } })

    expect(wrapper.get('pre').text()).toBe('{\n  "a": {\n    "b": 1\n  }\n}')
  })

  it('colors keys, strings, numbers and literals with different classes', () => {
    const wrapper = mountViewer({ k: 's', n: 1, t: true, z: null })
    const classFor = (kind: string) => wrapper.get(`[data-token="${kind}"]`).classes().join(' ')

    const classes = ['key', 'string', 'number', 'literal'].map(classFor)

    expect(new Set(classes).size).toBe(4)
    expect(wrapper.get('[data-token="key"]').text()).toBe('"k"')
    expect(wrapper.get('[data-token="string"]').text()).toBe('"s"')
    expect(wrapper.get('[data-token="number"]').text()).toBe('1')
    expect(wrapper.findAll('[data-token="literal"]').map((node) => node.text())).toEqual([
      'true',
      'null',
    ])
  })

  it('escapes html like strings instead of rendering them', () => {
    const wrapper = mountViewer({ title: '<img src=x onerror=alert(1)><b>bold</b>' })

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('b').exists()).toBe(false)
    expect(wrapper.get('pre').text()).toContain('<img src=x onerror=alert(1)><b>bold</b>')
  })

  it('keeps the JSON read only', () => {
    const wrapper = mountViewer({ a: 1 })

    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(wrapper.find('[contenteditable="true"]').exists()).toBe(false)
  })

  it('fills the height its parent gives it and scrolls inside', () => {
    const wrapper = mountViewer({ a: 1 })
    const scroll = scrollRegion(wrapper)

    expect(scroll.classes()).toContain('overflow-auto')
    expect(scroll.classes()).toContain('min-h-0')
    expect(scroll.classes()).toContain('flex-1')
    expect(scroll.classes().join(' ')).not.toMatch(/max-h-/)
    expect(wrapper.classes()).toEqual(
      expect.arrayContaining(['flex', 'flex-col', 'flex-1', 'h-full', 'min-h-0']),
    )
  })

  it('makes the scroll box a focusable region named JSON output', () => {
    const scroll = scrollRegion(mountViewer({ a: 1 }))

    expect(scroll.attributes('tabindex')).toBe('0')
    expect(scroll.attributes('role')).toBe('region')
    expect(scroll.attributes('aria-label')).toBe('JSON output')
  })

  it('names the region with the label it is given', () => {
    const wrapper = mountViewer({ a: 1 }, { label: 'Django dev JSON' })

    expect(scrollRegion(wrapper).attributes('aria-label')).toBe('Django dev JSON')
  })

  it('shows no title row, job count or button text', () => {
    const wrapper = mountViewer({ count: 12, jobs: [{}] })

    expect(wrapper.find('h4').exists()).toBe(false)
    expect(wrapper.find('[data-slot="json-title"]').exists()).toBe(false)
    expect(wrapper.find('[data-slot="json-count"]').exists()).toBe(false)
    expect(wrapper.findAll('button').map((button) => button.text())).toEqual(['', ''])
  })

  it('floats the fullscreen and copy buttons over the box, outside the scrolling content', () => {
    const wrapper = mountViewer({ a: 1 })
    const actions = wrapper.get('[data-slot="json-actions"]')

    expect(actions.findAll('button').map((button) => button.attributes('data-slot'))).toEqual([
      'json-fullscreen',
      'json-copy',
    ])
    expect(actions.classes()).toContain('absolute')
    expect(scrollRegion(wrapper).find('button').exists()).toBe(false)
    expect(actions.element.parentElement).toBe(scrollRegion(wrapper).element.parentElement)
    expect(actions.element.parentElement!.classList.contains('relative')).toBe(true)
  })

  it('puts a surface behind the buttons so the text does not show through', () => {
    const wrapper = mountViewer({ a: 1 })

    expect(wrapper.get('[data-slot="json-actions"]').classes()).toContain('bg-surface')
  })

  it('gives both icon buttons a name and hides the icons from screen readers', () => {
    const wrapper = mountViewer({ a: 1 })
    const buttons = wrapper.findAll('button')

    expect(buttons.map((button) => button.attributes('aria-label'))).toEqual([
      'Open full screen',
      'Copy JSON',
    ])
    expect(buttons.map((button) => button.attributes('type'))).toEqual(['button', 'button'])
    expect(buttons.map((button) => button.get('svg').attributes('aria-hidden'))).toEqual([
      'true',
      'true',
    ])
  })

  it('gives the buttons hover, focus and pressed styles', () => {
    const wrapper = mountViewer({ a: 1 })

    for (const button of wrapper.findAll('button')) {
      const classes = button.classes().join(' ')
      expect(classes).toMatch(/hover:/)
      expect(classes).toMatch(/focus-visible:focus-ring/)
      expect(classes).toMatch(/\bpress\b/)
    }
  })

  it('asks for full screen when the fullscreen button is clicked', async () => {
    const wrapper = mountViewer({ a: 1 })

    await wrapper.get('button[data-slot="json-fullscreen"]').trigger('click')

    expect(wrapper.emitted('fullscreen')).toHaveLength(1)
  })

  it('hides the fullscreen button when told to, and keeps the copy button', () => {
    const wrapper = mountViewer({ a: 1 }, { isFullscreenHidden: true })

    expect(wrapper.find('[data-slot="json-fullscreen"]').exists()).toBe(false)
    expect(wrapper.find('[data-slot="json-copy"]').exists()).toBe(true)
  })

  it('colors every token while the text is within the limit', () => {
    const wrapper = mountViewer({ a: 'x'.repeat(100) })

    expect(wrapper.findAll('[data-token]').length).toBeGreaterThan(0)
  })

  it('shows big payloads as plain pretty text without one node per token', () => {
    const value = oversizedValue()
    const wrapper = mountViewer(value)

    expect(prettyJson(value).length).toBeGreaterThan(MAX_HIGHLIGHT_CHARS)
    expect(wrapper.find('[data-token]').exists()).toBe(false)
    expect(wrapper.findAll('pre span')).toHaveLength(0)
    expect(wrapper.get('pre').text()).toBe(prettyJson(value))
  })

  it('still copies the full pretty json for a big payload', async () => {
    const writeText = resolvingClipboard()
    stubClipboard(writeText)
    const value = oversizedValue()
    const wrapper = mountViewer(value)

    await copyButton(wrapper).trigger('click')
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith(prettyJson(value))
  })

  it('clears the Copied timer when it goes away', async () => {
    stubClipboard(resolvingClipboard())
    const wrapper = mountViewer({ a: 1 })

    await copyButton(wrapper).trigger('click')
    await flushPromises()
    expect(vi.getTimerCount()).toBe(1)

    wrapper.unmount()

    expect(vi.getTimerCount()).toBe(0)
  })

  it('copies the pretty json and shows a check named Copied for 2 seconds', async () => {
    const writeText = resolvingClipboard()
    stubClipboard(writeText)
    const wrapper = mountViewer({ a: 1 })
    const button = copyButton(wrapper)
    expect(button.attributes('aria-label')).toBe('Copy JSON')
    expect(button.find('[data-icon="copy"]').exists()).toBe(true)

    await button.trigger('click')
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith('{\n  "a": 1\n}')
    expect(button.attributes('aria-label')).toBe('Copied')
    expect(button.find('[data-icon="check"]').exists()).toBe(true)
    expect(button.find('[data-icon="copy"]').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toBe('JSON copied')

    vi.advanceTimersByTime(FEEDBACK_MS - 1)
    await flushPromises()

    expect(button.attributes('aria-label')).toBe('Copied')

    vi.advanceTimersByTime(1)
    await flushPromises()

    expect(button.attributes('aria-label')).toBe('Copy JSON')
    expect(button.find('[data-icon="copy"]').exists()).toBe(true)
    expect(button.find('[data-icon="check"]').exists()).toBe(false)
  })

  it('copies the json it shows now, not the one it started with', async () => {
    const writeText = resolvingClipboard()
    stubClipboard(writeText)
    const wrapper = mountViewer({ a: 1 })

    await wrapper.setProps({ value: { b: 2 } })
    await copyButton(wrapper).trigger('click')
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith('{\n  "b": 2\n}')
  })

  it('shows a failure message when the clipboard rejects', async () => {
    stubClipboard(vi.fn<(text: string) => Promise<void>>().mockRejectedValue(new Error('denied')))
    const wrapper = mountViewer({ a: 1 })
    const button = copyButton(wrapper)

    await button.trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="status"]').text()).toBe(COPY_FAILED_MESSAGE)
    expect(button.attributes('aria-label')).toBe('Copy JSON')
    expect(button.find('[data-icon="copy"]').exists()).toBe(true)
  })

  it('takes the failure message away after 2 seconds', async () => {
    stubClipboard(vi.fn<(text: string) => Promise<void>>().mockRejectedValue(new Error('denied')))
    const wrapper = mountViewer({ a: 1 })

    await copyButton(wrapper).trigger('click')
    await flushPromises()
    vi.advanceTimersByTime(FEEDBACK_MS)
    await flushPromises()

    expect(wrapper.get('[role="status"]').text()).toBe('')
  })

  it('shows a failure message when there is no clipboard', async () => {
    vi.stubGlobal('navigator', {})
    const wrapper = mountViewer({ a: 1 })

    await copyButton(wrapper).trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="status"]').text()).toBe(COPY_FAILED_MESSAGE)
  })
})

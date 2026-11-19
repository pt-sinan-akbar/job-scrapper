import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'

import AuthLayout from '@/modules/auth/presentation/components/AuthLayout.vue'

function mountLayout() {
  return mount(AuthLayout, {
    global: { plugins: [createPinia()] },
    slots: { default: '<form data-testid="slot-form">Form</form>' },
  })
}

describe('AuthLayout', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn<MediaQueryList['addEventListener']>(),
        removeEventListener: vi.fn<MediaQueryList['removeEventListener']>(),
      })),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders slot content inside the form column in main', () => {
    const wrapper = mountLayout()

    const column = wrapper.get('main [data-testid="auth-column"]')

    expect(column.find('[data-testid="slot-form"]').exists()).toBe(true)
  })

  it('shows the product name in the compact header lockup, with no brand mark', () => {
    const wrapper = mountLayout()

    const lockup = wrapper.get('header [data-testid="auth-lockup"]')

    expect(lockup.text()).toBe('Job Agent Scraper')
    expect(lockup.find('svg').exists()).toBe(false)
  })

  it('renders the brand panel beside the form column', () => {
    const wrapper = mountLayout()

    const panel = wrapper.get('aside')

    expect(panel.get('[data-testid="brand-name"]').text()).toContain('Job Agent')
    expect(panel.find('[data-testid="auth-column"]').exists()).toBe(false)
  })

  it('renders the theme menu trigger in the header', () => {
    const wrapper = mountLayout()

    const trigger = wrapper.find('header button[aria-label^="Theme"]')

    expect(trigger.exists()).toBe(true)
  })

  it('contains no h1 of its own', () => {
    const wrapper = mountLayout()

    const headings = wrapper.findAll('h1')

    expect(headings).toHaveLength(0)
  })
})

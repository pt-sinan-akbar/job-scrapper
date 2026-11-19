import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import AuthBrandPanel from '@/modules/auth/presentation/components/AuthBrandPanel.vue'

describe('AuthBrandPanel', () => {
  it('sets the product name on two rows as its only text', () => {
    const wrapper = mount(AuthBrandPanel)

    const rows = wrapper.findAll('[data-testid="brand-name"] > span').map((row) => row.text())

    expect(rows).toEqual(['Job Agent', 'Scraper'])
    expect(wrapper.get('aside').text()).toBe(rows.join(''))
  })

  it('leaves the page heading to the form by holding no heading element', () => {
    const wrapper = mount(AuthBrandPanel)

    const headings = wrapper.findAll('h1, h2, h3, h4, h5, h6')

    expect(headings).toHaveLength(0)
  })

  it('hides the slab strip from assistive tech', () => {
    const wrapper = mount(AuthBrandPanel)

    const strip = wrapper.get('[data-testid="brand-slabs"]')

    expect(strip.attributes('aria-hidden')).toBe('true')
  })
})

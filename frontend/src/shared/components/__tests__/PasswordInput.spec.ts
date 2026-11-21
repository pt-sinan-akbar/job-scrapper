import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import PasswordInput from '@/shared/components/PasswordInput.vue'

function mountField(props: { isLabelHidden?: boolean } = {}) {
  return mount(PasswordInput, {
    props: { label: 'Password', modelValue: '', ...props },
  })
}

describe('PasswordInput', () => {
  it('shows the label above the field by default', () => {
    const wrapper = mountField()

    const label = wrapper.get('label')

    expect(label.text()).toBe('Password')
    expect(wrapper.find('.sr-only label').exists()).toBe(false)
  })

  it('keeps the label for screen readers only when it is hidden', () => {
    const wrapper = mountField({ isLabelHidden: true })

    const label = wrapper.get('.sr-only label')

    expect(label.text()).toBe('Password')
    expect(label.attributes('for')).toBe(wrapper.get('input').attributes('id'))
  })
})

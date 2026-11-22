import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'

import LocationPicker from '@/modules/config/presentation/components/LocationPicker.vue'

const OPTIONS = ['Jakarta', 'Tangerang', 'Tangerang Selatan', 'Bandung', 'Bekasi', 'Indonesia']

function stubBrowser(): void {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe = vi.fn<ResizeObserver['observe']>()
      unobserve = vi.fn<ResizeObserver['unobserve']>()
      disconnect = vi.fn<ResizeObserver['disconnect']>()
    },
  )
  Element.prototype.scrollIntoView = vi.fn()
}

type PickerWrapper = VueWrapper<InstanceType<typeof LocationPicker>>

const mounted: PickerWrapper[] = []

function mountPicker(modelValue: string[], options: string[] = OPTIONS): PickerWrapper {
  const wrapper = mount(LocationPicker, {
    props: { id: 'glints-locations', modelValue, options },
    attachTo: document.body,
  })
  mounted.push(wrapper)
  return wrapper
}

function lastUpdate(wrapper: PickerWrapper): string[] | undefined {
  const updates = wrapper.emitted('update:modelValue') ?? []
  return updates[updates.length - 1]?.[0] as string[] | undefined
}

function updates(wrapper: PickerWrapper): string[][] {
  return (wrapper.emitted('update:modelValue') ?? []).map((args) => args[0] as string[])
}

function chips(): HTMLElement[] {
  return Array.from(document.body.querySelectorAll<HTMLElement>('[data-slot="tags-input-item"]'))
}

function optionLabels(): string[] {
  const options = document.body.querySelectorAll('[role="option"]')
  return Array.from(options).map((option) => option.textContent?.trim() ?? '')
}

function findOption(label: string): Element | undefined {
  const options = Array.from(document.body.querySelectorAll('[role="option"]'))
  return options.find((option) => option.textContent?.trim() === label)
}

async function clickOption(label: string): Promise<void> {
  findOption(label)?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  await flushPromises()
}

async function openList(wrapper: PickerWrapper): Promise<void> {
  const input = wrapper.get('#glints-locations')
  await input.trigger('focus')
  await input.trigger('click')
  await flushPromises()
}

describe('LocationPicker', () => {
  beforeEach(stubBrowser)

  afterEach(() => {
    mounted.splice(0).forEach((wrapper) => wrapper.unmount())
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('shows the pick placeholder while no location is picked', () => {
    const wrapper = mountPicker([])

    expect(wrapper.get('#glints-locations').attributes('placeholder')).toBe('Pick locations')
    expect(chips()).toHaveLength(0)
  })

  it('shows no placeholder once a location is picked', () => {
    const wrapper = mountPicker(['Jakarta'])

    expect(wrapper.get('#glints-locations').attributes('placeholder')).toBe('')
  })

  it('shows a chip for each picked location', () => {
    mountPicker(['Jakarta', 'Tangerang Selatan'])

    expect(chips().map((chip) => chip.textContent?.trim())).toEqual([
      'Jakarta',
      'Tangerang Selatan',
    ])
  })

  it('lists the six options in the order given', async () => {
    const wrapper = mountPicker([])

    await openList(wrapper)

    expect(optionLabels()).toEqual(OPTIONS)
  })

  it('adds the option label when a location is chosen from the list', async () => {
    const wrapper = mountPicker(['Jakarta'])

    await openList(wrapper)
    await clickOption('Bandung')

    expect(lastUpdate(wrapper)).toEqual(['Jakarta', 'Bandung'])
  })

  it('lets Indonesia be picked together with cities', async () => {
    const wrapper = mountPicker(['Jakarta', 'Bekasi'])

    await openList(wrapper)
    await clickOption('Indonesia')

    expect(lastUpdate(wrapper)).toEqual(['Jakarta', 'Bekasi', 'Indonesia'])
  })

  it('marks the picked locations in the list', async () => {
    const wrapper = mountPicker(['Jakarta'])

    await openList(wrapper)

    const selected = document.body.querySelectorAll('[role="option"][data-state="checked"]')
    expect(Array.from(selected).map((option) => option.textContent?.trim())).toEqual(['Jakarta'])
  })

  it('names the location on each chip remove button', () => {
    mountPicker(['Tangerang Selatan'])

    const remove = chips()[0]?.querySelector('[data-slot="tags-input-item-delete"]')

    expect(remove?.getAttribute('aria-label')).toBe('Remove Tangerang Selatan')
  })

  it('still shows the saved values when the option list is empty', async () => {
    const wrapper = mountPicker(['jakarta', 'Atlantis'], [])

    await openList(wrapper)

    expect(chips().map((chip) => chip.textContent?.trim())).toEqual(['jakarta', 'Atlantis'])
    expect(optionLabels()).toEqual([])
    expect(document.body.textContent).toContain('No location found')
  })

  it('removes a location from the picked ones with its chip button', async () => {
    const wrapper = mountPicker(['Jakarta', 'Bandung'])

    const remove = chips()[0]?.querySelector<HTMLElement>('[data-slot="tags-input-item-delete"]')
    remove?.click()
    await flushPromises()

    expect(lastUpdate(wrapper)).toEqual(['Bandung'])
  })

  it('removes the last picked location, which leaves an empty selection', async () => {
    const wrapper = mountPicker(['Indonesia'])

    const remove = chips()[0]?.querySelector<HTMLElement>('[data-slot="tags-input-item-delete"]')
    remove?.click()
    await flushPromises()

    expect(lastUpdate(wrapper)).toEqual([])
  })

  it('filters the list by label while typing', async () => {
    const wrapper = mountPicker([])

    await openList(wrapper)
    await wrapper.get('#glints-locations').setValue('tAng')
    await flushPromises()

    expect(optionLabels()).toEqual(['Tangerang', 'Tangerang Selatan'])
  })

  it('does not accept a typed value that is not in the list', async () => {
    const wrapper = mountPicker([])

    await openList(wrapper)
    const input = wrapper.get('#glints-locations')
    await input.setValue('Atlantis')
    await input.trigger('keydown', { key: 'Enter' })
    const field = input.element as HTMLInputElement
    field.value = 'Atlantis,'
    field.dispatchEvent(new InputEvent('input', { data: ',', bubbles: true }))
    await flushPromises()

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(document.body.textContent).toContain('No location found')
  })

  it('emits exactly once with the new list when a location is chosen', async () => {
    const wrapper = mountPicker(['Jakarta'])

    await openList(wrapper)
    await clickOption('Bandung')

    expect(updates(wrapper)).toEqual([['Jakarta', 'Bandung']])
  })

  it('emits exactly once with the shorter list when a chip is removed', async () => {
    const wrapper = mountPicker(['Jakarta', 'Bandung'])

    chips()[0]?.querySelector<HTMLElement>('[data-slot="tags-input-item-delete"]')?.click()
    await flushPromises()

    expect(updates(wrapper)).toEqual([['Bandung']])
  })

  it('emits exactly once when a picked location is chosen again to unpick it', async () => {
    const wrapper = mountPicker(['Jakarta', 'Bandung'])

    await openList(wrapper)
    await clickOption('Jakarta')

    expect(updates(wrapper)).toEqual([['Bandung']])
  })

  it('picks the highlighted location with the keyboard', async () => {
    const wrapper = mountPicker([])

    await openList(wrapper)
    const input = wrapper.get('#glints-locations')
    await input.setValue('band')
    await flushPromises()
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'Enter' })
    await flushPromises()

    expect(updates(wrapper)).toEqual([['Bandung']])
  })

  it('ties the box to a hint when one is named', () => {
    const wrapper = mount(LocationPicker, {
      props: {
        id: 'glints-locations',
        modelValue: [],
        options: OPTIONS,
        describedBy: 'glints-locations-hint',
      },
      attachTo: document.body,
    })
    mounted.push(wrapper)

    expect(wrapper.get('#glints-locations').attributes('aria-describedby')).toBe(
      'glints-locations-hint',
    )
  })

  it('does not add a typed value on paste', async () => {
    const wrapper = mountPicker([])

    await openList(wrapper)
    const input = wrapper.get('#glints-locations')
    await input.setValue('Atlantis')
    const paste = new Event('paste', { bubbles: true, cancelable: true })
    Object.defineProperty(paste, 'clipboardData', {
      value: { getData: () => 'Atlantis' },
    })
    input.element.dispatchEvent(paste)
    await flushPromises()

    expect(updates(wrapper)).toEqual([])
    expect(chips()).toHaveLength(0)
  })

  it('does not add a typed value on blur', async () => {
    const wrapper = mountPicker([])

    await openList(wrapper)
    const input = wrapper.get('#glints-locations')
    await input.setValue('Atlantis')
    await input.trigger('blur')
    await flushPromises()

    expect(updates(wrapper)).toEqual([])
    expect(chips()).toHaveLength(0)
  })

  it('does not add a typed value on Tab', async () => {
    const wrapper = mountPicker([])

    await openList(wrapper)
    const input = wrapper.get('#glints-locations')
    await input.setValue('Atlantis')
    await input.trigger('keydown', { key: 'Tab' })
    await flushPromises()

    expect(updates(wrapper)).toEqual([])
    expect(chips()).toHaveLength(0)
  })
})

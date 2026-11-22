import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import { EMPTY_FILTER, type SiteSetting } from '@/modules/config/domain/entities/ScraperConfig'
import SiteSettings from '@/modules/config/presentation/components/SiteSettings.vue'

const SITES: SiteSetting[] = [
  {
    name: 'glints',
    isEnabled: true,
    limit: 30,
    maxAgeHours: 72,
    urlTemplate: null,
    filter: EMPTY_FILTER,
    api: { isEnabled: true, delayMin: null, delayMax: null },
  },
  {
    name: 'indeed',
    isEnabled: false,
    limit: 10,
    maxAgeHours: null,
    urlTemplate: null,
    filter: EMPTY_FILTER,
    api: null,
  },
  {
    name: 'linkedin',
    isEnabled: true,
    limit: 5,
    maxAgeHours: 24,
    urlTemplate: null,
    filter: EMPTY_FILTER,
    api: null,
  },
]

const LOCATION_OPTIONS = ['Jakarta', 'Bandung', 'Indonesia']

function mountSettings(sites: SiteSetting[] = SITES) {
  return mount(SiteSettings, {
    props: { sites, locationOptions: LOCATION_OPTIONS },
    attachTo: document.body,
  })
}

type Wrapper = ReturnType<typeof mountSettings>

function selectButton(wrapper: Wrapper, name: string) {
  return wrapper
    .findAll('[data-slot="site-select"]')
    .find((button) => button.get('[data-slot="site-name"]').text() === name)!
}

function selectedName(wrapper: Wrapper): string | undefined {
  return wrapper
    .find('[data-slot="site-select"][aria-current="true"] [data-slot="site-name"]')
    .text()
}

function lastUpdate(wrapper: Wrapper): SiteSetting | undefined {
  const updates = wrapper.emitted('update') ?? []
  return updates[updates.length - 1]?.[0] as SiteSetting | undefined
}

function stubResizeObserver(): void {
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

function optionLabels(): string[] {
  const options = document.body.querySelectorAll('[role="option"]')
  return Array.from(options).map((option) => option.textContent?.trim() ?? '')
}

async function openLocationList(wrapper: Wrapper, siteName: string): Promise<void> {
  const input = wrapper.get(`#${siteName}-location`)
  await input.trigger('focus')
  await input.trigger('click')
  await flushPromises()
}

describe('SiteSettings filter locations', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('offers the same location options to every site, with or without an API', async () => {
    stubResizeObserver()
    const wrapper = mountSettings()

    await openLocationList(wrapper, 'glints')
    const glintsOptions = optionLabels()
    await selectButton(wrapper, 'linkedin').trigger('click')
    await flushPromises()
    await openLocationList(wrapper, 'linkedin')
    const linkedinOptions = optionLabels()
    wrapper.unmount()

    expect(glintsOptions).toEqual(LOCATION_OPTIONS)
    expect(linkedinOptions).toEqual(LOCATION_OPTIONS)
  })
})

describe('SiteSettings list and detail', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('lists every site by its name only', () => {
    const wrapper = mountSettings()

    expect(selectButton(wrapper, 'glints').text()).toBe('glints')
    expect(selectButton(wrapper, 'indeed').text()).toBe('indeed')
  })

  it('picks the first site on load', () => {
    const wrapper = mountSettings()

    expect(selectedName(wrapper)).toBe('glints')
    expect(wrapper.find('#glints-limit').exists()).toBe(true)
    expect(wrapper.find('#indeed-limit').exists()).toBe(false)
  })

  it('marks only the picked site as current and ties it to the detail', () => {
    const wrapper = mountSettings()
    const current = wrapper.findAll('[aria-current="true"]')
    const panelId = current[0]!.attributes('aria-controls')

    expect(current).toHaveLength(1)
    expect(selectButton(wrapper, 'indeed').attributes('aria-current')).toBeUndefined()
    expect(wrapper.get(`[id="${panelId}"]`).text()).toContain('glints')
  })

  it('shows the settings of a clicked site', async () => {
    const wrapper = mountSettings()

    await selectButton(wrapper, 'indeed').trigger('click')

    expect(selectedName(wrapper)).toBe('indeed')
    expect(wrapper.find('#indeed-limit').exists()).toBe(true)
    expect(wrapper.find('#glints-limit').exists()).toBe(false)
  })

  it.each([
    ['ArrowDown', 'glints', 'indeed'],
    ['ArrowRight', 'glints', 'indeed'],
    ['ArrowUp', 'indeed', 'glints'],
    ['ArrowLeft', 'indeed', 'glints'],
    ['ArrowUp', 'glints', 'linkedin'],
    ['ArrowDown', 'linkedin', 'glints'],
    ['End', 'glints', 'linkedin'],
    ['Home', 'linkedin', 'glints'],
  ])('moves the pick with %s from %s to %s', async (key, from, to) => {
    const wrapper = mountSettings()
    await selectButton(wrapper, from).trigger('click')

    await selectButton(wrapper, from).trigger('keydown', { key })
    await flushPromises()

    expect(selectedName(wrapper)).toBe(to)
    expect(document.activeElement).toBe(selectButton(wrapper, to).element)
  })

  it.each(['altKey', 'ctrlKey', 'metaKey', 'shiftKey'])(
    'ignores arrow keys pressed with %s',
    async (modifier) => {
      const wrapper = mountSettings()

      await selectButton(wrapper, 'glints').trigger('keydown', {
        key: 'ArrowDown',
        [modifier]: true,
      })
      await flushPromises()

      expect(selectedName(wrapper)).toBe('glints')
    },
  )

  it('pads the phone chip row so focus rings are not cut off', () => {
    const list = mountSettings().get('ul[aria-label="Sites"]')

    expect(list.classes()).toEqual(expect.arrayContaining(['px-2', 'py-1']))
  })

  it('ignores other keys', async () => {
    const wrapper = mountSettings()

    await selectButton(wrapper, 'glints').trigger('keydown', { key: 'a' })

    expect(selectedName(wrapper)).toBe('glints')
  })

  it('shows no on and off checkbox in the site list', () => {
    const list = mountSettings().get('ul[aria-label="Sites"]')

    expect(list.find('[data-slot="checkbox"]').exists()).toBe(false)
    expect(list.find('[aria-label^="Turn on"]').exists()).toBe(false)
  })

  it('builds safe ids for a site name with spaces and symbols', () => {
    const wrapper = mountSettings([{ ...SITES[1]!, name: 'Job Street (ID)' }])

    expect(wrapper.find('#job-street-id-limit').exists()).toBe(true)
    expect(wrapper.get('label[for="job-street-id-limit"]').text()).toBe('Job limit')
    expect(wrapper.find('#job-street-id-location').exists()).toBe(true)
  })

  it('keeps the pick when the sites change', async () => {
    const wrapper = mountSettings()
    await selectButton(wrapper, 'indeed').trigger('click')

    await wrapper.setProps({ sites: SITES.map((site) => ({ ...site, limit: 7 })) })

    expect(selectedName(wrapper)).toBe('indeed')
  })

  it('falls back to the first site when the picked one is gone', async () => {
    const wrapper = mountSettings()
    await selectButton(wrapper, 'indeed').trigger('click')

    await wrapper.setProps({ sites: [SITES[2]!, SITES[0]!] })

    expect(selectedName(wrapper)).toBe('linkedin')
  })

  it('does not jump back to a removed site when it comes back', async () => {
    const wrapper = mountSettings()
    await selectButton(wrapper, 'indeed').trigger('click')

    await wrapper.setProps({ sites: [SITES[0]!, SITES[2]!] })
    await wrapper.setProps({ sites: SITES })

    expect(selectedName(wrapper)).toBe('glints')
  })

  it('selects the site named by a save issue and marks its field', async () => {
    const wrapper = mountSettings()

    await wrapper.setProps({
      issue: { siteName: 'linkedin', field: 'maxAgeHours', message: 'Bad max age' },
    })

    expect(selectedName(wrapper)).toBe('linkedin')
    expect(wrapper.get('#linkedin-max-age').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('#linkedin-limit').attributes('aria-invalid')).toBeUndefined()
  })

  it('shows nothing to pick when there are no sites', () => {
    const wrapper = mountSettings([])

    expect(wrapper.find('[data-slot="site-select"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('No sites')
  })
})

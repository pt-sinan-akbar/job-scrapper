import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'

import { EMPTY_FILTER, type SiteSetting } from '@/modules/config/domain/entities/ScraperConfig'
import SiteDetail from '@/modules/config/presentation/components/SiteDetail.vue'

const SITE: SiteSetting = {
  name: 'glints',
  isEnabled: true,
  limit: 3,
  maxAgeHours: null,
  urlTemplate: null,
  filter: EMPTY_FILTER,
  api: null,
}

const LOCATION_OPTIONS = [
  'Jakarta',
  'Tangerang',
  'Tangerang Selatan',
  'Bandung',
  'Bekasi',
  'Indonesia',
]

const NO_LOCATION_HINT = 'No location picked: searches all of Indonesia'

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

type DetailWrapper = VueWrapper<InstanceType<typeof SiteDetail>>

const mountedDetails: DetailWrapper[] = []

function mountDetail(props: InstanceType<typeof SiteDetail>['$props']): DetailWrapper {
  stubResizeObserver()
  const wrapper = mount(SiteDetail, { props, attachTo: document.body })
  mountedDetails.push(wrapper)
  return wrapper
}

function mountSite(site: SiteSetting, locationOptions: string[] = LOCATION_OPTIONS): DetailWrapper {
  return mountDetail({ site, locationOptions })
}

function unmountDetails(): void {
  mountedDetails.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
}

function withLocations(location: string[]): SiteSetting {
  return { ...SITE, filter: { ...EMPTY_FILTER, location } }
}

function chipLabels(): string[] {
  const chips = document.body.querySelectorAll('[data-slot="tags-input-item"]')
  return Array.from(chips).map((chip) => chip.textContent?.trim() ?? '')
}

function optionLabels(): string[] {
  const options = document.body.querySelectorAll('[role="option"]')
  return Array.from(options).map((option) => option.textContent?.trim() ?? '')
}

async function openLocationList(wrapper: DetailWrapper): Promise<void> {
  const input = wrapper.get('#glints-location')
  await input.trigger('focus')
  await input.trigger('click')
  await flushPromises()
}

async function clickLocationOption(label: string): Promise<void> {
  const options = Array.from(document.body.querySelectorAll('[role="option"]'))
  const option = options.find((candidate) => candidate.textContent?.trim() === label)
  option?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  await flushPromises()
}

function lastToggle(wrapper: {
  emitted: (event: string) => unknown[][] | undefined
}): unknown[] | undefined {
  const toggles = wrapper.emitted('toggle') ?? []
  return toggles[toggles.length - 1]
}

function lastUpdate(wrapper: DetailWrapper): SiteSetting | undefined {
  const updates = wrapper.emitted('update') ?? []
  return updates[updates.length - 1]?.[0] as SiteSetting | undefined
}

describe('SiteDetail job fields', () => {
  afterEach(unmountDetails)

  it('has no job fields of its own, since every site uses the global list', () => {
    const wrapper = mountSite(SITE)

    expect(wrapper.find('#glints-own-fields').exists()).toBe(false)
    expect(wrapper.find('[id^="glints-field-"]').exists()).toBe(false)
  })
})

const API_SITE: SiteSetting = {
  ...SITE,
  api: { isEnabled: true, delayMin: null, delayMax: null },
}

describe('SiteDetail filter locations', () => {
  afterEach(unmountDetails)

  it('labels the location pick list plainly', () => {
    const wrapper = mountSite(SITE)

    expect(wrapper.get('label[for="glints-location"]').text()).toBe('Locations')
    expect(wrapper.text()).not.toContain('Locations, separated by commas')
  })

  it('shows a chip for each picked location', () => {
    mountSite(withLocations(['Jakarta', 'Tangerang Selatan']))

    expect(chipLabels()).toEqual(['Jakarta', 'Tangerang Selatan'])
  })

  it('offers the options it was given, also for a site with no API', async () => {
    const wrapper = mountSite(SITE)

    await openLocationList(wrapper)

    expect(optionLabels()).toEqual(LOCATION_OPTIONS)
  })

  it('sends the option label of a picked location in the filter', async () => {
    const wrapper = mountSite(withLocations(['Jakarta']))

    await openLocationList(wrapper)
    await clickLocationOption('Indonesia')

    expect(lastUpdate(wrapper)?.filter).toEqual({
      ...EMPTY_FILTER,
      location: ['Jakarta', 'Indonesia'],
    })
  })

  it('does not take typed text as a location', async () => {
    const wrapper = mountSite(SITE)

    await wrapper.get('#glints-location').setValue('Atlantis, Jakarta')
    await wrapper.get('#glints-location').trigger('blur')
    await flushPromises()

    expect(wrapper.emitted('update')).toBeUndefined()
  })

  it('says the whole country is searched while no location is picked', () => {
    const wrapper = mountSite(SITE)

    expect(wrapper.get('#glints-location-hint').text()).toBe(NO_LOCATION_HINT)
  })

  it('ties the whole country hint to the location box', () => {
    const wrapper = mountSite(SITE)

    expect(wrapper.get('#glints-location').attributes('aria-describedby')).toBe(
      'glints-location-hint',
    )
  })

  it('hides the whole country hint once a location is picked', () => {
    const wrapper = mountSite(withLocations(['Bekasi']))

    expect(wrapper.find('#glints-location-hint').exists()).toBe(false)
    expect(wrapper.text()).not.toContain(NO_LOCATION_HINT)
    expect(wrapper.get('#glints-location').attributes('aria-describedby')).toBeUndefined()
  })

  it('keeps the saved values on show when the option list is empty', () => {
    mountSite(withLocations(['jakarta', 'Atlantis']), [])

    expect(chipLabels()).toEqual(['jakarta', 'Atlantis'])
  })

  it('keeps employment types and work types as free text', async () => {
    const wrapper = mountSite(SITE)

    await wrapper.get('#glints-employment').setValue('contract, full time')

    expect(wrapper.get('label[for="glints-employment"]').text()).toBe(
      'Employment types, separated by commas',
    )
    expect(wrapper.get('label[for="glints-work"]').text()).toBe('Work types, separated by commas')
    expect(lastUpdate(wrapper)?.filter.employmentType).toEqual(['contract', 'full time'])
  })
})

describe('SiteDetail API group', () => {
  afterEach(unmountDetails)

  it('has no API locations picker', () => {
    const wrapper = mountSite(API_SITE)

    expect(wrapper.find('#glints-api-locations').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('API locations')
  })

  it('has no whole country checkbox', () => {
    const wrapper = mountSite(API_SITE)

    expect(wrapper.find('#glints-api-country').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Also search the whole country')
  })

  it('never warns that the site finds nothing', () => {
    const wrapper = mountSite(API_SITE)

    expect(wrapper.text()).not.toContain('this site finds nothing')
  })

  it('keeps the API switch and both delay boxes', () => {
    const wrapper = mountSite(API_SITE)

    expect(wrapper.get('label[for="glints-api-enabled"]').text()).toBe('Use the API')
    expect(wrapper.find('#glints-api-delay-min').exists()).toBe(true)
    expect(wrapper.find('#glints-api-delay-max').exists()).toBe(true)
  })

  it('gives each empty text and number box a placeholder', () => {
    const wrapper = mountSite({ ...API_SITE, limit: null })

    expect(wrapper.get('#glints-api-delay-min').attributes('placeholder')).toBe('Min delay')
    expect(wrapper.get('#glints-api-delay-max').attributes('placeholder')).toBe('Max delay')
    expect(wrapper.get('#glints-limit').attributes('placeholder')).toBe('1 to 200')
    expect(wrapper.get('#glints-max-age').attributes('placeholder')).toBe('Any age')
    expect(wrapper.get('#glints-location').attributes('placeholder')).toBe('Pick locations')
    expect(wrapper.get('#glints-employment').attributes('placeholder')).toBe('Employment types')
    expect(wrapper.get('#glints-work').attributes('placeholder')).toBe('Work types')
  })
})

describe('SiteDetail delay', () => {
  afterEach(unmountDetails)

  it('labels both delay boxes and lets them use the full width', () => {
    const wrapper = mountSite(API_SITE)

    expect(wrapper.get('label[for="glints-api-delay-min"]').text()).toBe('Min delay in seconds')
    expect(wrapper.get('label[for="glints-api-delay-max"]').text()).toBe('Max delay in seconds')
    expect(wrapper.get('#glints-api-delay-min').classes()).not.toContain('w-24')
    expect(wrapper.get('#glints-api-delay-max').classes()).not.toContain('w-24')
  })

  it('keeps the other delay value when one changes', async () => {
    const wrapper = mountSite({
      ...API_SITE,
      api: { ...API_SITE.api!, delayMin: 2, delayMax: 5 },
    })

    await wrapper.get('#glints-api-delay-max').setValue('8')

    expect(lastUpdate(wrapper)?.api).toMatchObject({ delayMin: 2, delayMax: 8 })
  })

  it('does not copy one delay value into the empty other one', async () => {
    const wrapper = mountSite(API_SITE)

    await wrapper.get('#glints-api-delay-max').setValue('8')

    expect(lastUpdate(wrapper)?.api).toMatchObject({ delayMin: null, delayMax: 8 })
  })

  it('lets the min delay go above the max delay for the save check to catch', async () => {
    const wrapper = mountSite({
      ...API_SITE,
      api: { ...API_SITE.api!, delayMin: 2, delayMax: 5 },
    })

    await wrapper.get('#glints-api-delay-min').setValue('9')

    expect(lastUpdate(wrapper)?.api).toMatchObject({ delayMin: 9, delayMax: 5 })
  })

  it('takes half seconds as a delay', async () => {
    const wrapper = mountSite(API_SITE)

    await wrapper.get('#glints-api-delay-min').setValue('1.5')

    expect(lastUpdate(wrapper)?.api?.delayMin).toBe(1.5)
  })

  it('marks the delay box named by a save issue', () => {
    const wrapper = mountDetail({
      site: API_SITE,
      locationOptions: LOCATION_OPTIONS,
      invalidField: 'delayMax',
    })

    expect(wrapper.get('#glints-api-delay-max').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('#glints-api-delay-min').attributes('aria-invalid')).toBeUndefined()
  })
})

function legends(wrapper: DetailWrapper): string[] {
  return wrapper.findAll('[data-slot="site-group"] > legend').map((legend) => legend.text())
}

describe('SiteDetail basics and filter', () => {
  afterEach(unmountDetails)

  it('groups the settings under labelled headings', () => {
    expect(legends(mountSite(SITE))).toEqual(['Source', 'Basics', 'Filter'])
  })

  it('adds an API group for sites with an API', () => {
    expect(legends(mountSite(API_SITE))).toEqual(['Source', 'Basics', 'Filter', 'API'])
  })

  it('makes the limit a required whole number box', () => {
    const limit = mountSite(SITE).get('#glints-limit')

    expect(limit.attributes('required')).toBeDefined()
    expect(limit.attributes('inputmode')).toBe('numeric')
    expect((limit.element as HTMLInputElement).value).toBe('3')
  })

  it('keeps half typed text in the box without sending it', async () => {
    const wrapper = mountSite(SITE)
    const limit = wrapper.get('#glints-limit')

    await limit.setValue('1e')

    expect((limit.element as HTMLInputElement).value).toBe('1e')
    expect(wrapper.emitted('update')).toBeUndefined()
    expect(limit.attributes('aria-invalid')).toBe('true')
  })

  it('does not send a decimal limit', async () => {
    const wrapper = mountSite(SITE)

    await wrapper.get('#glints-limit').setValue('2.5')

    expect(wrapper.emitted('update')).toBeUndefined()
  })

  it('sends the number once the typed text is a whole number again', async () => {
    const wrapper = mountSite(SITE)
    const limit = wrapper.get('#glints-limit')

    await limit.setValue('1e')
    await limit.setValue('12')

    expect(lastUpdate(wrapper)?.limit).toBe(12)
  })

  it('puts the saved value back when leaving a box with half typed text', async () => {
    const wrapper = mountSite(SITE)
    const limit = wrapper.get('#glints-limit')

    await limit.setValue('1e')
    await limit.trigger('blur')

    expect((limit.element as HTMLInputElement).value).toBe('3')
    expect(limit.attributes('aria-invalid')).toBeUndefined()
  })

  it('shows a value changed from outside', async () => {
    const wrapper = mountSite(SITE)

    await wrapper.setProps({ site: { ...SITE, limit: 9 } })

    expect((wrapper.get('#glints-limit').element as HTMLInputElement).value).toBe('9')
  })

  it('sends a typed limit as a number', async () => {
    const wrapper = mountSite(SITE)

    await wrapper.get('#glints-limit').setValue('40')

    expect(lastUpdate(wrapper)?.limit).toBe(40)
  })

  it('does not require a max age', () => {
    expect(mountSite(SITE).get('#glints-max-age').attributes('required')).toBeUndefined()
  })

  it('turns an emptied max age into null, for no age cut', async () => {
    const wrapper = mountSite({ ...SITE, maxAgeHours: 48 })

    await wrapper.get('#glints-max-age').setValue('')

    expect(lastUpdate(wrapper)?.maxAgeHours).toBeNull()
  })

  it('always shows the filter fields, with no own filter switch', () => {
    const wrapper = mountSite(SITE)

    expect(wrapper.find('#glints-location').exists()).toBe(true)
    expect(wrapper.find('#glints-employment').exists()).toBe(true)
    expect(wrapper.find('#glints-work').exists()).toBe(true)
    expect(wrapper.find('#glints-own-filter').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Use its own filter')
  })

  it('sends an edited filter', async () => {
    const wrapper = mountSite(SITE)

    await wrapper.get('#glints-work').setValue('remote, hybrid')

    expect(lastUpdate(wrapper)?.filter).toEqual({ ...EMPTY_FILTER, workType: ['remote', 'hybrid'] })
  })

  it('never shows the word Global', () => {
    expect(mountSite(SITE).html()).not.toContain('Global')
  })
})

const URL_TEMPLATE =
  'https://glints.com/id/opportunities/jobs/explore?keyword={keyword}&locationName={location}'

describe('SiteDetail source', () => {
  afterEach(unmountDetails)

  it('shows the URL template read only', () => {
    const wrapper = mountSite({ ...SITE, urlTemplate: URL_TEMPLATE })

    const template = wrapper.get('#glints-url-template')

    expect(template.text()).toBe(URL_TEMPLATE)
    expect(template.element.tagName).not.toBe('INPUT')
    expect(wrapper.get('#glints-url-template-label').text()).toBe('URL template')
    expect(template.attributes('aria-labelledby')).toBe('glints-url-template-label')
  })

  it('says there is no URL template when it is missing', () => {
    const wrapper = mountSite(SITE)

    expect(wrapper.get('#glints-url-template').text()).toBe('No URL template')
  })

  it('shows No API when the site has no API', () => {
    const wrapper = mountSite(SITE)

    expect(wrapper.get('#glints-api-status').text()).toBe('No API')
    expect(wrapper.get('#glints-api-status').attributes('aria-labelledby')).toBe(
      'glints-api-status-label',
    )
  })

  it('shows API on when the site API is enabled', () => {
    const wrapper = mountSite(API_SITE)

    expect(wrapper.get('#glints-api-status').text()).toBe('API on')
  })

  it('asks to save the API toggle at once when Use the API is unchecked', async () => {
    const wrapper = mountSite(API_SITE)

    await wrapper.get('#glints-api-enabled').trigger('click')

    expect(lastToggle(wrapper)).toEqual([{ siteName: 'glints', field: 'apiEnabled', isOn: false }])
    expect(wrapper.emitted('update')).toBeUndefined()
  })

  it('shows API off once the saved site has the API turned off', async () => {
    const wrapper = mountSite(API_SITE)

    await wrapper.setProps({ site: { ...API_SITE, api: { ...API_SITE.api!, isEnabled: false } } })

    expect(wrapper.get('#glints-api-status').text()).toBe('API off')
  })
})

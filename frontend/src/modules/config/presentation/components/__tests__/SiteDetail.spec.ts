import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

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

function mountSite(site: SiteSetting) {
  return mount(SiteDetail, {
    props: { site },
    attachTo: document.body,
  })
}

function lastToggle(wrapper: {
  emitted: (event: string) => unknown[][] | undefined
}): unknown[] | undefined {
  const toggles = wrapper.emitted('toggle') ?? []
  return toggles[toggles.length - 1]
}

function lastUpdate(wrapper: ReturnType<typeof mountSite>): SiteSetting | undefined {
  const updates = wrapper.emitted('update') ?? []
  return updates[updates.length - 1]?.[0] as SiteSetting | undefined
}

describe('SiteDetail job fields', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('has no job fields of its own, since every site uses the global list', () => {
    const wrapper = mountSite(SITE)

    expect(wrapper.find('#glints-own-fields').exists()).toBe(false)
    expect(wrapper.find('[id^="glints-field-"]').exists()).toBe(false)
  })
})

const API_SITE: SiteSetting = {
  ...SITE,
  api: { isEnabled: true, locations: [], isCountryWide: false, delayMin: null, delayMax: null },
}

const LOCATION_OPTIONS = [
  { label: 'Jakarta', value: '78d63064-78a1-4577-8516-036a6c5e903e' },
  { label: 'Bandung', value: 'bandung-id' },
]

const EMPTY_WARNING = 'No city and no country search: this site finds nothing'

function mountApiSite(site: SiteSetting, locationOptions?: typeof LOCATION_OPTIONS) {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe = vi.fn<ResizeObserver['observe']>()
      unobserve = vi.fn<ResizeObserver['unobserve']>()
      disconnect = vi.fn<ResizeObserver['disconnect']>()
    },
  )
  return mount(SiteDetail, {
    props: { site, locationOptions },
    attachTo: document.body,
  })
}

describe('SiteDetail API locations', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('shows no locations box when the site has no city list', () => {
    const wrapper = mountApiSite({ ...API_SITE, api: { ...API_SITE.api!, locations: ['Remote'] } })

    expect(wrapper.find('#glints-api-locations').exists()).toBe(false)
    expect(wrapper.text()).not.toContain(EMPTY_WARNING)
  })

  it('shows no locations box when the city list is empty', () => {
    const wrapper = mountApiSite({ ...API_SITE, api: { ...API_SITE.api!, locations: [] } }, [])

    expect(wrapper.find('#glints-api-locations').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('API locations')
    expect(wrapper.text()).not.toContain(EMPTY_WARNING)
  })

  it('shows the city picker with chips for the saved values', () => {
    const wrapper = mountApiSite(
      { ...API_SITE, api: { ...API_SITE.api!, locations: [LOCATION_OPTIONS[0]!.value] } },
      LOCATION_OPTIONS,
    )

    expect(wrapper.find('#glints-api-locations').exists()).toBe(true)
    expect(wrapper.text()).toContain('API locations')
    expect(wrapper.text()).not.toContain('one per line')
    expect(wrapper.text()).toContain('Jakarta')
  })

  it('warns when no city is picked and the whole country is off', () => {
    const wrapper = mountApiSite(API_SITE, LOCATION_OPTIONS)

    expect(wrapper.text()).toContain(EMPTY_WARNING)
  })

  it('does not warn when the whole country is searched', () => {
    const wrapper = mountApiSite(
      { ...API_SITE, api: { ...API_SITE.api!, isCountryWide: true } },
      LOCATION_OPTIONS,
    )

    expect(wrapper.text()).not.toContain(EMPTY_WARNING)
  })

  it('does not warn when a city is picked', () => {
    const wrapper = mountApiSite(
      { ...API_SITE, api: { ...API_SITE.api!, locations: ['bandung-id'] } },
      LOCATION_OPTIONS,
    )

    expect(wrapper.text()).not.toContain(EMPTY_WARNING)
  })

  it('gives each empty text and number box a placeholder', () => {
    const wrapper = mountApiSite({ ...API_SITE, limit: null }, LOCATION_OPTIONS)

    expect(wrapper.get('#glints-api-delay-min').attributes('placeholder')).toBe('Min delay')
    expect(wrapper.get('#glints-api-delay-max').attributes('placeholder')).toBe('Max delay')
    expect(wrapper.get('#glints-limit').attributes('placeholder')).toBe('1 to 200')
    expect(wrapper.get('#glints-max-age').attributes('placeholder')).toBe('Any age')
    expect(wrapper.get('#glints-location').attributes('placeholder')).toBe('Locations')
    expect(wrapper.get('#glints-employment').attributes('placeholder')).toBe('Employment types')
    expect(wrapper.get('#glints-work').attributes('placeholder')).toBe('Work types')
  })
})

describe('SiteDetail delay', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('labels both delay boxes and lets them use the full width', () => {
    const wrapper = mountApiSite(API_SITE)

    expect(wrapper.get('label[for="glints-api-delay-min"]').text()).toBe('Min delay in seconds')
    expect(wrapper.get('label[for="glints-api-delay-max"]').text()).toBe('Max delay in seconds')
    expect(wrapper.get('#glints-api-delay-min').classes()).not.toContain('w-24')
    expect(wrapper.get('#glints-api-delay-max').classes()).not.toContain('w-24')
  })

  it('keeps the other delay value when one changes', async () => {
    const wrapper = mountApiSite({
      ...API_SITE,
      api: { ...API_SITE.api!, delayMin: 2, delayMax: 5 },
    })

    await wrapper.get('#glints-api-delay-max').setValue('8')

    expect(lastUpdate(wrapper)?.api).toMatchObject({ delayMin: 2, delayMax: 8 })
  })

  it('does not copy one delay value into the empty other one', async () => {
    const wrapper = mountApiSite(API_SITE)

    await wrapper.get('#glints-api-delay-max').setValue('8')

    expect(lastUpdate(wrapper)?.api).toMatchObject({ delayMin: null, delayMax: 8 })
  })

  it('lets the min delay go above the max delay for the save check to catch', async () => {
    const wrapper = mountApiSite({
      ...API_SITE,
      api: { ...API_SITE.api!, delayMin: 2, delayMax: 5 },
    })

    await wrapper.get('#glints-api-delay-min').setValue('9')

    expect(lastUpdate(wrapper)?.api).toMatchObject({ delayMin: 9, delayMax: 5 })
  })

  it('takes half seconds as a delay', async () => {
    const wrapper = mountApiSite(API_SITE)

    await wrapper.get('#glints-api-delay-min').setValue('1.5')

    expect(lastUpdate(wrapper)?.api?.delayMin).toBe(1.5)
  })

  it('marks the delay box named by a save issue', () => {
    const wrapper = mount(SiteDetail, {
      props: { site: API_SITE, invalidField: 'delayMax' },
      attachTo: document.body,
    })

    expect(wrapper.get('#glints-api-delay-max').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('#glints-api-delay-min').attributes('aria-invalid')).toBeUndefined()
  })
})

function legends(wrapper: ReturnType<typeof mountSite>): string[] {
  return wrapper.findAll('[data-slot="site-group"] > legend').map((legend) => legend.text())
}

describe('SiteDetail basics and filter', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('groups the settings under labelled headings', () => {
    expect(legends(mountSite(SITE))).toEqual(['Source', 'Basics', 'Filter'])
  })

  it('adds an API group for sites with an API', () => {
    expect(legends(mountApiSite(API_SITE))).toEqual(['Source', 'Basics', 'Filter', 'API'])
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
  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

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
    const wrapper = mountApiSite(API_SITE)

    expect(wrapper.get('#glints-api-status').text()).toBe('API on')
  })

  it('asks to save the API toggle at once when Use the API is unchecked', async () => {
    const wrapper = mountApiSite(API_SITE)

    await wrapper.get('#glints-api-enabled').trigger('click')

    expect(lastToggle(wrapper)).toEqual([{ siteName: 'glints', field: 'apiEnabled', isOn: false }])
    expect(wrapper.emitted('update')).toBeUndefined()
  })

  it('asks to save the whole country toggle at once', async () => {
    const wrapper = mountApiSite(API_SITE)
    const isCountryWide = API_SITE.api?.isCountryWide ?? false

    await wrapper.get('#glints-api-country').trigger('click')

    expect(lastToggle(wrapper)).toEqual([
      { siteName: 'glints', field: 'apiCountryWide', isOn: !isCountryWide },
    ])
  })

  it('shows API off once the saved site has the API turned off', async () => {
    const wrapper = mountApiSite(API_SITE)

    await wrapper.setProps({ site: { ...API_SITE, api: { ...API_SITE.api!, isEnabled: false } } })

    expect(wrapper.get('#glints-api-status').text()).toBe('API off')
  })
})

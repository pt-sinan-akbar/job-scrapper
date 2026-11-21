import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import { EMPTY_FILTER, type ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
import ConfigForm from '@/modules/config/presentation/components/ConfigForm.vue'
import { provideConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'

const getConfig = { execute: vi.fn() }
const saveConfig = { execute: vi.fn() }

const SNAPSHOT: ConfigSnapshot = {
  values: {
    fields: ['title'],
    sites: [
      {
        name: 'upwork',
        isEnabled: true,
        limit: 3,
        maxAgeHours: 72,
        filter: EMPTY_FILTER,
        api: null,
      },
      {
        name: 'indeed',
        isEnabled: false,
        limit: 10,
        maxAgeHours: null,
        filter: EMPTY_FILTER,
        api: null,
      },
    ],
  },
  version: 4,
  updatedAt: '2026-11-02T01:00:00+00:00',
  updatedBy: 'ui',
  isStale: false,
  jobFields: ['site', 'title', 'company'],
  mandatoryFields: ['site', 'company'],
  locationOptions: {},
}

async function mountForm(props: { isSaveBarSticky?: boolean } = {}, snapshot = SNAPSHOT) {
  getConfig.execute.mockResolvedValue(snapshot)
  const store = useConfigStore()
  await store.load()
  const wrapper = mount(ConfigForm, { props, attachTo: document.body })
  await flushPromises()
  return { wrapper, store }
}

function findButton(wrapper: Awaited<ReturnType<typeof mountForm>>['wrapper'], label: string) {
  return wrapper.findAll('button').find((button) => button.text() === label)
}

describe('ConfigForm', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    provideConfigUseCases({ getConfig, saveConfig })
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('keeps the field ids the config page always had', async () => {
    const { wrapper } = await mountForm()

    for (const id of [
      '#default-field-title',
      '#upwork-limit',
      '#upwork-max-age',
      '#upwork-location',
    ]) {
      expect(wrapper.find(id).exists(), id).toBe(true)
    }
  })

  it('has no keywords field and no General section', async () => {
    const { wrapper } = await mountForm()

    expect(wrapper.find('#keywords').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('General')
    expect(wrapper.text()).not.toContain('Keywords')
  })

  it('has no global job settings', async () => {
    const { wrapper } = await mountForm()

    for (const id of ['#limit', '#max-age', '#concurrency', '#bot-schedule', '#global-location']) {
      expect(wrapper.find(id).exists(), id).toBe(false)
    }
    expect(wrapper.text()).not.toContain('Global filter')
    expect(wrapper.text()).not.toContain('Bot schedule')
    expect(wrapper.text()).not.toContain('Sites scraped at once')
  })

  it('shows no turned on count under Sites', async () => {
    const { wrapper } = await mountForm()

    expect(wrapper.text()).not.toContain('turned on')
  })

  it('saves a change to the site picked in the list', async () => {
    saveConfig.execute.mockResolvedValue(undefined)
    const { wrapper } = await mountForm()
    const indeed = wrapper
      .findAll('[data-slot="site-select"]')
      .find((button) => button.text().includes('indeed'))!

    await indeed.trigger('click')
    await wrapper.get('#indeed-limit').setValue('25')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveConfig.execute).toHaveBeenCalledWith({ sites: { indeed: { limit: 25 } } }, 4)
  })

  it('sends null for an emptied max age, for no age cut', async () => {
    saveConfig.execute.mockResolvedValue(undefined)
    const { wrapper } = await mountForm()

    await wrapper.get('#upwork-max-age').setValue('')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveConfig.execute).toHaveBeenCalledWith({ sites: { upwork: { maxAgeHours: null } } }, 4)
  })

  it('blocks the save and says why when a site has no limit', async () => {
    const { wrapper } = await mountForm()

    await wrapper.get('#upwork-limit').setValue('')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveConfig.execute).not.toHaveBeenCalled()
    expect(wrapper.get('[data-slot="save-bar"] [role="alert"]').text()).toBe(
      'Set a limit from 1 to 200 for upwork',
    )
  })

  it('selects a hidden site with a bad max age and blocks the save', async () => {
    const { wrapper, store } = await mountForm()
    store.values!.sites[1]!.maxAgeHours = 0
    await flushPromises()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveConfig.execute).not.toHaveBeenCalled()
    expect(wrapper.get('[data-slot="save-bar"] [role="alert"]').text()).toBe(
      'Set a max job age from 1 to 720 hours for indeed, or leave it empty',
    )
    expect(
      wrapper.get('[data-slot="site-select"][aria-current="true"] [data-slot="site-name"]').text(),
    ).toBe('indeed')
    expect(wrapper.get('#indeed-max-age').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('#indeed-limit').attributes('aria-invalid')).toBeUndefined()

    await wrapper.get('#indeed-max-age').setValue('24')
    await flushPromises()

    expect(wrapper.find('[data-slot="save-bar"] [role="alert"]').exists()).toBe(false)
    expect(wrapper.get('#indeed-max-age').attributes('aria-invalid')).toBeUndefined()
  })

  it('has no older versions section', async () => {
    const { wrapper } = await mountForm()

    expect(wrapper.text()).not.toContain('Older versions')
    expect(findButton(wrapper, 'Restore')).toBeUndefined()
  })

  it('renders nothing before the config is loaded', () => {
    const wrapper = mount(ConfigForm)

    expect(wrapper.find('form').exists()).toBe(false)
  })

  it('has Discard disabled until a value changes', async () => {
    const { wrapper } = await mountForm()
    const discard = findButton(wrapper, 'Discard')!

    expect(discard.attributes('disabled')).toBeDefined()

    await wrapper.get('#upwork-limit').setValue('9')

    expect(discard.attributes('disabled')).toBeUndefined()
  })

  it('puts the values back when Discard is pressed', async () => {
    const { wrapper, store } = await mountForm()
    await wrapper.get('#upwork-limit').setValue('9')

    await findButton(wrapper, 'Discard')!.trigger('click')

    expect(store.values?.sites[0]?.limit).toBe(3)
    expect((wrapper.get('#upwork-limit').element as HTMLInputElement).value).toBe('3')
    expect(findButton(wrapper, 'Discard')!.attributes('disabled')).toBeDefined()
  })

  it('does not submit the form when Discard is pressed', async () => {
    const { wrapper } = await mountForm()
    await wrapper.get('#upwork-limit').setValue('9')

    await findButton(wrapper, 'Discard')!.trigger('click')

    expect(saveConfig.execute).not.toHaveBeenCalled()
  })

  it('disables Discard while a save is running', async () => {
    const { wrapper, store } = await mountForm()
    await wrapper.get('#upwork-limit').setValue('9')

    store.isSaving = true
    await flushPromises()

    expect(findButton(wrapper, 'Discard')!.attributes('disabled')).toBeDefined()
  })

  it('sticks the save bar to the page bottom by default', async () => {
    const { wrapper } = await mountForm()

    expect(wrapper.get('[data-slot="save-bar"]').classes()).toContain('sticky')
  })

  it('leaves the save bar in the flow when it is not sticky', async () => {
    const { wrapper } = await mountForm({ isSaveBarSticky: false })

    expect(wrapper.get('[data-slot="save-bar"]').classes()).not.toContain('sticky')
  })

  it('shows the busy notice and turns Save off when the scraper is stale', async () => {
    const { wrapper } = await mountForm({}, { ...SNAPSHOT, isStale: true })

    expect(wrapper.text()).toContain('The scraper is busy')
    expect(findButton(wrapper, 'Save')!.attributes('disabled')).toBeDefined()
  })

  it('shows the save error next to the buttons', async () => {
    const { wrapper, store } = await mountForm()

    store.saveError = 'Conflict'
    await flushPromises()

    expect(wrapper.get('[data-slot="save-bar"] [role="alert"]').text()).toBe('Conflict')
  })

  it('saves the changed values on submit', async () => {
    saveConfig.execute.mockResolvedValue(undefined)
    const { wrapper } = await mountForm()
    await wrapper.get('#upwork-limit').setValue('9')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveConfig.execute).toHaveBeenCalledWith({ sites: { upwork: { limit: 9 } } }, 4)
  })
})

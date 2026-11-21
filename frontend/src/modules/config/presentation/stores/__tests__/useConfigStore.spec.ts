import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { EMPTY_FILTER, type ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
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
        urlTemplate: null,
        filter: EMPTY_FILTER,
        api: null,
      },
    ],
  },
  version: 4,
  updatedAt: '2026-11-02T01:00:00+00:00',
  updatedBy: 'ui',
  isStale: false,
  jobFields: ['site', 'title', 'company', 'salary_min', 'company_id'],
  mandatoryFields: ['site', 'company'],
  locationOptions: {},
}

describe('useConfigStore', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    provideConfigUseCases({ getConfig, saveConfig })
  })

  it('loads a copy of the values', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const store = useConfigStore()

    await store.load()

    expect(store.status).toBe('ready')
    expect(store.values).toEqual(SNAPSHOT.values)
    expect(store.values).not.toBe(SNAPSHOT.values)
    expect(store.values?.sites[0]).not.toBe(SNAPSHOT.values.sites[0])
  })

  it('shows an error when load fails', async () => {
    getConfig.execute.mockRejectedValue(new Error('Scraper down'))
    const store = useConfigStore()

    await store.load()

    expect(store.status).toBe('error')
    expect(store.errorMessage).toBe('Scraper down')
  })

  it('saves changed values with the loaded version then reloads', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    saveConfig.execute.mockResolvedValue(undefined)
    const store = useConfigStore()
    await store.load()
    store.values!.sites[0]!.limit = 9

    await expect(store.save()).resolves.toBe(true)

    expect(saveConfig.execute).toHaveBeenCalledWith({ sites: { upwork: { limit: 9 } } }, 4)
    expect(getConfig.execute).toHaveBeenCalledTimes(2)
  })

  it('skips the save when nothing changed', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const store = useConfigStore()
    await store.load()

    await expect(store.save()).resolves.toBe(true)

    expect(saveConfig.execute).not.toHaveBeenCalled()
  })

  it('keeps the message when save fails', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    saveConfig.execute.mockRejectedValue(new Error('Bad config'))
    const store = useConfigStore()
    await store.load()
    store.values!.sites[0]!.limit = 9

    await expect(store.save()).resolves.toBe(false)

    expect(store.saveError).toBe('Bad config')
  })

  it('does not save stale values', async () => {
    getConfig.execute.mockResolvedValue({ ...SNAPSHOT, isStale: true })
    const store = useConfigStore()
    await store.load()
    store.values!.sites[0]!.limit = 9

    await expect(store.save()).resolves.toBe(false)

    expect(saveConfig.execute).not.toHaveBeenCalled()
  })

  it.each([null, 0, 201])(
    'blocks the save and names the site when its limit is %s',
    async (limit) => {
      getConfig.execute.mockResolvedValue(SNAPSHOT)
      const store = useConfigStore()
      await store.load()
      store.values!.sites[0]!.limit = limit

      await expect(store.save()).resolves.toBe(false)

      expect(saveConfig.execute).not.toHaveBeenCalled()
      expect(store.saveError).toBe('Set a limit from 1 to 200 for upwork')
    },
  )

  describe('site checks on save', () => {
    const TWO_SITES: ConfigSnapshot = {
      ...SNAPSHOT,
      values: {
        ...SNAPSHOT.values,
        sites: [
          SNAPSHOT.values.sites[0]!,
          {
            ...SNAPSHOT.values.sites[0]!,
            name: 'glints',
            api: {
              isEnabled: true,
              locations: [],
              isCountryWide: true,
              delayMin: 2,
              delayMax: 5,
            },
          },
        ],
      },
    }

    async function loadTwoSites() {
      getConfig.execute.mockResolvedValue(TWO_SITES)
      const store = useConfigStore()
      await store.load()
      return store
    }

    it.each([0, 721, 2.5])(
      'blocks the save and names any site whose max age is %s',
      async (maxAgeHours) => {
        const store = await loadTwoSites()
        store.values!.sites[1]!.maxAgeHours = maxAgeHours

        await expect(store.save()).resolves.toBe(false)

        expect(saveConfig.execute).not.toHaveBeenCalled()
        expect(store.saveError).toBe(
          'Set a max job age from 1 to 720 hours for glints, or leave it empty',
        )
        expect(store.siteIssue).toEqual({
          siteName: 'glints',
          field: 'maxAgeHours',
          message: 'Set a max job age from 1 to 720 hours for glints, or leave it empty',
        })
      },
    )

    it.each<[number | null, number | null, string]>([
      [null, 5, 'Set both delay values for glints'],
      [-1, 5, 'Set delays from 0 to 60 seconds for glints'],
      [2, 61, 'Set delays from 0 to 60 seconds for glints'],
      [6, 5, 'Set a min delay no higher than the max delay for glints'],
    ])('blocks the save for delay %s to %s', async (delayMin, delayMax, message) => {
      const store = await loadTwoSites()
      store.values!.sites[1]!.api = { ...store.values!.sites[1]!.api!, delayMin, delayMax }

      await expect(store.save()).resolves.toBe(false)

      expect(saveConfig.execute).not.toHaveBeenCalled()
      expect(store.saveError).toBe(message)
    })

    it('sends the delay as a pair when both values are valid', async () => {
      saveConfig.execute.mockResolvedValue(undefined)
      const store = await loadTwoSites()
      store.values!.sites[1]!.api = { ...store.values!.sites[1]!.api!, delayMin: 1, delayMax: 9 }

      await expect(store.save()).resolves.toBe(true)

      expect(saveConfig.execute).toHaveBeenCalledWith(
        {
          sites: {
            glints: {
              api: {
                isEnabled: true,
                locations: [],
                isCountryWide: true,
                delayMin: 1,
                delayMax: 9,
              },
            },
          },
        },
        4,
      )
    })

    it('clears the save error once the bad value is fixed', async () => {
      const store = await loadTwoSites()
      store.values!.sites[1]!.maxAgeHours = 0
      await store.save()

      store.values!.sites[1]!.maxAgeHours = 24
      await nextTick()

      expect(store.saveError).toBeNull()
      expect(store.siteIssue).toBeNull()
    })

    it('keeps the save error while the bad value stays bad', async () => {
      const store = await loadTwoSites()
      store.values!.sites[1]!.maxAgeHours = 0
      await store.save()

      store.values!.sites[0]!.limit = 9
      await nextTick()

      expect(store.saveError).toBe(
        'Set a max job age from 1 to 720 hours for glints, or leave it empty',
      )
    })

    it('clears the site issue on discard', async () => {
      const store = await loadTwoSites()
      store.values!.sites[1]!.maxAgeHours = 0
      await store.save()

      store.discard()

      expect(store.siteIssue).toBeNull()
      expect(store.saveError).toBeNull()
    })
  })

  it('has no history or restore', () => {
    const store = useConfigStore()

    expect('history' in store).toBe(false)
    expect('loadHistory' in store).toBe(false)
    expect('restore' in store).toBe(false)
  })

  it('is not dirty before a load', () => {
    const store = useConfigStore()

    expect(store.isDirty).toBe(false)
  })

  it('is not dirty right after a load', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const store = useConfigStore()

    await store.load()

    expect(store.isDirty).toBe(false)
  })

  it('is dirty once a value differs from the snapshot', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const store = useConfigStore()
    await store.load()

    store.values!.sites[0]!.limit = 9

    expect(store.isDirty).toBe(true)
  })

  it('is dirty when a nested value changes', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const store = useConfigStore()
    await store.load()

    store.values!.sites[0]!.filter.location.push('Jakarta')

    expect(store.isDirty).toBe(true)
  })

  it('is not dirty again when an edit is put back', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const store = useConfigStore()
    await store.load()
    store.values!.sites[0]!.limit = 9

    store.values!.sites[0]!.limit = 3

    expect(store.isDirty).toBe(false)
  })

  it('discards edits back to the snapshot values', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const store = useConfigStore()
    await store.load()
    store.values!.sites[0]!.limit = 9
    store.values!.fields.push('company')

    store.discard()

    expect(store.values).toEqual(SNAPSHOT.values)
    expect(store.isDirty).toBe(false)
  })

  it('keeps the snapshot untouched when discarding then editing again', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const store = useConfigStore()
    await store.load()
    store.discard()

    store.values!.fields.push('company')

    expect(store.snapshot?.values.fields).toEqual(['title'])
    expect(store.isDirty).toBe(true)
  })

  it('does nothing when discarding before a load', () => {
    const store = useConfigStore()

    store.discard()

    expect(store.values).toBeNull()
  })

  it('clears the save error when discarding', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    saveConfig.execute.mockRejectedValue(new Error('Conflict'))
    const store = useConfigStore()
    await store.load()
    store.values!.sites[0]!.limit = 9
    await store.save()

    store.discard()

    expect(store.saveError).toBeNull()
  })

  describe('auto save', () => {
    const API_SNAPSHOT: ConfigSnapshot = {
      ...SNAPSHOT,
      values: {
        ...SNAPSHOT.values,
        sites: [
          {
            ...SNAPSHOT.values.sites[0]!,
            api: {
              isEnabled: true,
              locations: ['jakarta'],
              isCountryWide: false,
              delayMin: 1,
              delayMax: 2,
            },
          },
        ],
      },
    }

    function savedSnapshot(next: Partial<ConfigSnapshot['values']>, version = 5): ConfigSnapshot {
      return { ...SNAPSHOT, version, values: { ...SNAPSHOT.values, ...next } }
    }

    it('saves picked job fields at once and leaves nothing to save', async () => {
      getConfig.execute
        .mockResolvedValueOnce(SNAPSHOT)
        .mockResolvedValueOnce(savedSnapshot({ fields: ['title', 'salary_min'] }))
      saveConfig.execute.mockResolvedValue(undefined)
      const store = useConfigStore()
      await store.load()

      await expect(store.saveJobFields(['title', 'salary_min'])).resolves.toBe(true)

      expect(saveConfig.execute).toHaveBeenCalledWith({ fields: ['title', 'salary_min'] }, 4)
      expect(store.values?.fields).toEqual(['title', 'salary_min'])
      expect(store.snapshot?.version).toBe(5)
      expect(store.isDirty).toBe(false)
    })

    it('saves a site switched off at once', async () => {
      const offSites = [{ ...SNAPSHOT.values.sites[0]!, isEnabled: false }]
      getConfig.execute
        .mockResolvedValueOnce(SNAPSHOT)
        .mockResolvedValueOnce(savedSnapshot({ sites: offSites }))
      saveConfig.execute.mockResolvedValue(undefined)
      const store = useConfigStore()
      await store.load()

      await store.saveSiteToggle({ siteName: 'upwork', field: 'isEnabled', isOn: false })

      expect(saveConfig.execute).toHaveBeenCalledWith(
        { sites: { upwork: { isEnabled: false } } },
        4,
      )
      expect(store.values?.sites[0]?.isEnabled).toBe(false)
      expect(store.isDirty).toBe(false)
    })

    it('saves only the API toggle, not unsaved API edits', async () => {
      getConfig.execute.mockResolvedValue(API_SNAPSHOT)
      saveConfig.execute.mockResolvedValue(undefined)
      const store = useConfigStore()
      await store.load()
      store.values!.sites[0]!.api!.delayMax = 9

      await store.saveSiteToggle({ siteName: 'upwork', field: 'apiCountryWide', isOn: true })

      expect(saveConfig.execute).toHaveBeenCalledWith(
        {
          sites: {
            upwork: { api: { ...API_SNAPSHOT.values.sites[0]!.api!, isCountryWide: true } },
          },
        },
        4,
      )
    })

    it('keeps other unsaved edits after an auto save', async () => {
      getConfig.execute
        .mockResolvedValueOnce(SNAPSHOT)
        .mockResolvedValueOnce(savedSnapshot({ fields: ['title', 'company_id'] }))
      saveConfig.execute.mockResolvedValue(undefined)
      const store = useConfigStore()
      await store.load()
      store.values!.sites[0]!.limit = 9

      await store.saveJobFields(['title', 'company_id'])

      expect(store.values?.sites[0]?.limit).toBe(9)
      expect(store.values?.fields).toEqual(['title', 'company_id'])
      expect(store.isDirty).toBe(true)
    })

    it('puts the checkbox back and keeps the error when the save fails', async () => {
      getConfig.execute.mockResolvedValue(SNAPSHOT)
      saveConfig.execute.mockRejectedValue(new Error('Config changed elsewhere'))
      const store = useConfigStore()
      await store.load()

      await expect(store.saveJobFields(['title', 'salary_min'])).resolves.toBe(false)

      expect(store.values?.fields).toEqual(['title'])
      expect(store.autoSaveError).toBe('Config changed elsewhere')
      expect(store.isDirty).toBe(false)
    })

    it('saves fast clicks one after another with the newest version', async () => {
      getConfig.execute
        .mockResolvedValueOnce(SNAPSHOT)
        .mockResolvedValueOnce(savedSnapshot({ fields: ['title', 'salary_min'] }, 5))
        .mockResolvedValueOnce(savedSnapshot({ fields: ['title', 'salary_min', 'company_id'] }, 6))
      saveConfig.execute.mockResolvedValue(undefined)
      const store = useConfigStore()
      await store.load()

      const first = store.saveJobFields(['title', 'salary_min'])
      const second = store.saveJobFields(['title', 'salary_min', 'company_id'])
      await Promise.all([first, second])

      expect(saveConfig.execute).toHaveBeenNthCalledWith(1, { fields: ['title', 'salary_min'] }, 4)
      expect(saveConfig.execute).toHaveBeenNthCalledWith(
        2,
        { fields: ['title', 'salary_min', 'company_id'] },
        5,
      )
      expect(store.isDirty).toBe(false)
    })

    it('does not save while the scraper is busy', async () => {
      getConfig.execute.mockResolvedValue({ ...SNAPSHOT, isStale: true })
      const store = useConfigStore()
      await store.load()

      await expect(store.saveJobFields(['title', 'salary_min'])).resolves.toBe(false)

      expect(saveConfig.execute).not.toHaveBeenCalled()
      expect(store.values?.fields).toEqual(['title'])
    })
  })
})

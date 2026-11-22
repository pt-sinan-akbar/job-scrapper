import { describe, expect, it } from 'vitest'
import type { ApiSetting } from '@/modules/config/domain/entities/ScraperConfig'
import {
  toConfigChangesModel,
  toConfigSnapshot,
  type ConfigModel,
} from '@/modules/config/data/models/ConfigModel'

const MODEL: ConfigModel = {
  values: {
    fields: ['title'],
    sites: [
      {
        name: 'upwork',
        enabled: true,
        limit: 30,
        max_age_hours: null,
        filter: {},
        api: {},
        url_template: 'https://www.upwork.com/nx/search/jobs/?q={keyword}',
      },
      {
        name: 'indeed',
        enabled: false,
        limit: 10,
        max_age_hours: 24,
        filter: { location: ['jakarta'] },
        api: null,
      },
    ],
  },
  version: 4,
  updated_at: '2026-11-02T01:00:00+00:00',
  updated_by: 'ui',
  is_stale: false,
  job_fields: ['site', 'title', 'location', 'salary_min'],
  mandatory_fields: ['site'],
}

const LOCATION_OPTIONS = [
  'Jakarta',
  'Tangerang',
  'Tangerang Selatan',
  'Bandung',
  'Bekasi',
  'Indonesia',
]

function withSavedLocations(savedLocations: string[], locationOptions: unknown): ConfigModel {
  const [upwork] = MODEL.values.sites
  return {
    ...MODEL,
    values: { ...MODEL.values, sites: [{ ...upwork!, filter: { location: savedLocations } }] },
    location_options: locationOptions,
  } as ConfigModel
}

function readLocations(model: ConfigModel): string[] | undefined {
  return toConfigSnapshot(model).values.sites[0]?.filter.location
}

describe('toConfigSnapshot', () => {
  it('maps API names', () => {
    const snapshot = toConfigSnapshot(MODEL)

    expect(snapshot.version).toBe(4)
    expect(snapshot.updatedBy).toBe('ui')
    expect(snapshot.values.fields).toEqual(['title'])
  })

  it('has no global job settings and no keywords', () => {
    expect(Object.keys(toConfigSnapshot(MODEL).values).sort()).toEqual(['fields', 'sites'])
  })

  it('ignores keywords from an older API response', () => {
    const model = { ...MODEL, values: { ...MODEL.values, keywords: ['django'] } } as ConfigModel

    expect(toConfigSnapshot(model).values).not.toHaveProperty('keywords')
  })

  it('reads the limit and max age of each site', () => {
    const [upwork, indeed] = toConfigSnapshot(MODEL).values.sites

    expect(upwork?.limit).toBe(30)
    expect(upwork?.maxAgeHours).toBeNull()
    expect(indeed?.limit).toBe(10)
    expect(indeed?.maxAgeHours).toBe(24)
  })

  it('reads the URL template of each site', () => {
    const [upwork] = toConfigSnapshot(MODEL).values.sites

    expect(upwork?.urlTemplate).toBe('https://www.upwork.com/nx/search/jobs/?q={keyword}')
  })

  it('reads a missing URL template as null', () => {
    const [, indeed] = toConfigSnapshot(MODEL).values.sites

    expect(indeed?.urlTemplate).toBeNull()
  })

  it('reads a null URL template as null', () => {
    const [upwork] = MODEL.values.sites
    const model: ConfigModel = {
      ...MODEL,
      values: { ...MODEL.values, sites: [{ ...upwork!, url_template: null }] },
    }

    expect(toConfigSnapshot(model).values.sites[0]?.urlTemplate).toBeNull()
  })

  it('lists the job fields and the always-saved ones', () => {
    const snapshot = toConfigSnapshot(MODEL)

    expect(snapshot.jobFields).toEqual(['site', 'title', 'location', 'salary_min'])
    expect(snapshot.mandatoryFields).toEqual(['site'])
  })

  it('drops unknown and always-saved names from the picked job fields', () => {
    const model: ConfigModel = {
      ...MODEL,
      values: { ...MODEL.values, fields: ['site', 'salary_min', 'old_field', 'title'] },
    }

    const { values } = toConfigSnapshot(model)

    expect(values.fields).toEqual(['salary_min', 'title'])
  })

  it('gives sites no job fields of their own', () => {
    const [upwork] = toConfigSnapshot(MODEL).values.sites

    expect(upwork).not.toHaveProperty('fields')
  })

  it('always gives each site a filter with every list filled', () => {
    const [upwork, indeed] = toConfigSnapshot(MODEL).values.sites

    expect(upwork?.filter).toEqual({ location: [], employmentType: [], workType: [] })
    expect(indeed?.filter).toEqual({ location: ['jakarta'], employmentType: [], workType: [] })
  })

  it('fills api defaults', () => {
    const [upwork, indeed] = toConfigSnapshot(MODEL).values.sites

    expect(upwork?.api).toEqual({ isEnabled: true, delayMin: null, delayMax: null })
    expect(indeed?.api).toBeNull()
  })

  it('ignores the locations and country switch of an older saved api block', () => {
    const [upwork] = MODEL.values.sites
    const oldApi = { enabled: false, locations: ['Remote'], country_wide: true }
    const model = {
      ...MODEL,
      values: { ...MODEL.values, sites: [{ ...upwork!, api: oldApi }] },
    } as ConfigModel

    expect(toConfigSnapshot(model).values.sites[0]?.api).toEqual({
      isEnabled: false,
      delayMin: null,
      delayMax: null,
    })
  })

  it('splits the saved delay into a min and a max value', () => {
    const model: ConfigModel = {
      ...MODEL,
      values: {
        ...MODEL.values,
        sites: MODEL.values.sites.map((site) =>
          site.api === null ? site : { ...site, api: { ...site.api, delay_seconds: [2, 5] } },
        ),
      },
    }
    const [upwork] = toConfigSnapshot(model).values.sites

    expect(upwork?.api?.delayMin).toBe(2)
    expect(upwork?.api?.delayMax).toBe(5)
  })
})

describe('toConfigSnapshot location options', () => {
  it('reads the list of location labels', () => {
    const model: ConfigModel = { ...MODEL, location_options: LOCATION_OPTIONS }

    expect(toConfigSnapshot(model).locationOptions).toEqual(LOCATION_OPTIONS)
  })

  it('treats a missing location_options key as an empty list', () => {
    expect(toConfigSnapshot(MODEL).locationOptions).toEqual([])
  })

  it.each([null, 'Jakarta', 5, { glints: [{ label: 'Jakarta', value: 'jakarta' }] }])(
    'treats a location_options of %o as an empty list',
    (locationOptions) => {
      const model = { ...MODEL, location_options: locationOptions } as unknown as ConfigModel

      expect(toConfigSnapshot(model).locationOptions).toEqual([])
    },
  )

  it('skips entries that are not text', () => {
    const model = {
      ...MODEL,
      location_options: ['Jakarta', 5, null, { label: 'Bandung' }, 'Indonesia'],
    } as unknown as ConfigModel

    expect(toConfigSnapshot(model).locationOptions).toEqual(['Jakarta', 'Indonesia'])
  })
})

describe('toConfigSnapshot filter locations', () => {
  it('turns saved values of any case into the option labels', () => {
    const model = withSavedLocations(
      ['jakarta', 'tangerang selatan', 'INDONESIA', 'Bekasi'],
      LOCATION_OPTIONS,
    )

    expect(readLocations(model)).toEqual(['Jakarta', 'Tangerang Selatan', 'Indonesia', 'Bekasi'])
  })

  it('drops saved values that match no option', () => {
    const model = withSavedLocations(['jakarta', 'Atlantis', 'tangerang sel'], LOCATION_OPTIONS)

    expect(readLocations(model)).toEqual(['Jakarta'])
  })

  it('keeps one label when two saved values match the same option', () => {
    const model = withSavedLocations(['jakarta', 'Jakarta', 'bandung'], LOCATION_OPTIONS)

    expect(readLocations(model)).toEqual(['Jakarta', 'Bandung'])
  })

  it('keeps the saved values as they are when the option list is missing', () => {
    const model = withSavedLocations(['jakarta', 'Atlantis'], undefined)

    expect(readLocations(model)).toEqual(['jakarta', 'Atlantis'])
  })

  it('keeps the saved values as they are when the option list is malformed', () => {
    const model = withSavedLocations(['jakarta', 'Atlantis'], { glints: [] })

    expect(readLocations(model)).toEqual(['jakarta', 'Atlantis'])
  })
})

describe('toConfigChangesModel', () => {
  it('maps changed fields to API names', () => {
    const model = toConfigChangesModel({
      fields: ['title'],
      sites: {
        upwork: {
          isEnabled: false,
          limit: 20,
          maxAgeHours: null,
          filter: {
            location: ['Jakarta', 'Tangerang Selatan'],
            employmentType: ['contract'],
            workType: [],
          },
          api: { isEnabled: true, delayMin: 4, delayMax: 6 },
        },
      },
    })

    expect(model).toEqual({
      fields: ['title'],
      sites: {
        upwork: {
          enabled: false,
          limit: 20,
          max_age_hours: null,
          filter: {
            location: ['Jakarta', 'Tangerang Selatan'],
            employment_type: ['contract'],
            work_type: [],
          },
          api: { enabled: true, delay_seconds: [4, 6] },
        },
      },
    })
  })

  it('sends no delay when both delay values are empty', () => {
    const model = toConfigChangesModel({
      sites: {
        upwork: {
          api: { isEnabled: true, delayMin: null, delayMax: null },
        },
      },
    })

    expect(model.sites?.upwork?.api?.delay_seconds).toBeNull()
  })

  it('never sends api locations or a country switch', () => {
    const staleApi = {
      isEnabled: false,
      delayMin: null,
      delayMax: null,
      locations: ['Remote'],
      isCountryWide: true,
    } as ApiSetting

    const model = toConfigChangesModel({ sites: { upwork: { api: staleApi } } })

    expect(model.sites?.upwork?.api).toEqual({ enabled: false, delay_seconds: null })
  })

  it('sends empty lists for no filter', () => {
    const filter = { location: [], employmentType: [], workType: [] }

    expect(toConfigChangesModel({ sites: { upwork: { filter } } })).toEqual({
      sites: { upwork: { filter: { location: [], employment_type: [], work_type: [] } } },
    })
  })

  it('leaves out fields that did not change', () => {
    expect(toConfigChangesModel({ fields: ['url'] })).toEqual({ fields: ['url'] })
  })
})

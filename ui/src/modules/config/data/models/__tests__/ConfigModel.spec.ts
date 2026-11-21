import { describe, expect, it } from 'vitest'
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
        api: { locations: ['Remote'] },
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

    expect(upwork?.api).toEqual({
      isEnabled: true,
      locations: ['Remote'],
      isCountryWide: false,
      delayMin: null,
      delayMax: null,
    })
    expect(indeed?.api).toBeNull()
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
  it('maps the city list of each site', () => {
    const model: ConfigModel = {
      ...MODEL,
      location_options: {
        glints: [
          { label: 'Jakarta', value: '78d63064' },
          { label: 'Bandung', value: 'bandung-id' },
        ],
      },
    }

    expect(toConfigSnapshot(model).locationOptions).toEqual({
      glints: [
        { label: 'Jakarta', value: '78d63064' },
        { label: 'Bandung', value: 'bandung-id' },
      ],
    })
  })

  it('treats a missing location_options key as no lists', () => {
    expect(toConfigSnapshot(MODEL).locationOptions).toEqual({})
  })

  it('skips a malformed list and malformed entries', () => {
    const model = {
      ...MODEL,
      location_options: {
        glints: [
          { label: 'Jakarta', value: 'ok' },
          { label: 5, value: 'x' },
          null,
          { label: 'No value' },
        ],
        jobstreet: 'oops',
        linkedin: null,
      },
    } as unknown as ConfigModel

    expect(toConfigSnapshot(model).locationOptions).toEqual({
      glints: [{ label: 'Jakarta', value: 'ok' }],
    })
  })

  it('treats a location_options that is not an object as no lists', () => {
    const model = { ...MODEL, location_options: [] } as unknown as ConfigModel

    expect(toConfigSnapshot(model).locationOptions).toEqual({})
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
          filter: { location: [], employmentType: ['contract'], workType: [] },
          api: {
            isEnabled: true,
            locations: ['Remote'],
            isCountryWide: true,
            delayMin: 4,
            delayMax: 6,
          },
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
          filter: { location: [], employment_type: ['contract'], work_type: [] },
          api: { enabled: true, locations: ['Remote'], country_wide: true, delay_seconds: [4, 6] },
        },
      },
    })
  })

  it('sends no delay when both delay values are empty', () => {
    const model = toConfigChangesModel({
      sites: {
        upwork: {
          api: {
            isEnabled: true,
            locations: [],
            isCountryWide: true,
            delayMin: null,
            delayMax: null,
          },
        },
      },
    })

    expect(model.sites?.upwork?.api?.delay_seconds).toBeNull()
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

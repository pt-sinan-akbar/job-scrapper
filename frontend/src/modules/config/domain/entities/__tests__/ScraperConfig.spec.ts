import { describe, expect, it } from 'vitest'
import {
  EMPTY_FILTER,
  DELAY_SECONDS_MAX,
  findSiteIssue,
  hasConfigChanges,
  MAX_AGE_HOURS_MAX,
  SITE_LIMIT_MAX,
  toConfigChanges,
  toDelaySeconds,
  toApiStatus,
  toApiStatusLabel,
  toJobFieldLabel,
  type ApiSetting,
  type ConfigValues,
  type SiteSetting,
} from '@/modules/config/domain/entities/ScraperConfig'

const SITE: SiteSetting = {
  name: 'upwork',
  isEnabled: true,
  limit: 30,
  maxAgeHours: 72,
  urlTemplate: 'https://www.upwork.com/nx/search/jobs/?q={keyword}',
  filter: EMPTY_FILTER,
  api: {
    isEnabled: true,
    locations: ['Remote'],
    isCountryWide: false,
    delayMin: null,
    delayMax: null,
  },
}

const ORIGINAL: ConfigValues = {
  fields: ['title'],
  sites: [SITE],
}

function withSite(changes: Partial<SiteSetting>): ConfigValues {
  return { ...ORIGINAL, sites: [{ ...SITE, ...changes }] }
}

function withApi(changes: Partial<ApiSetting>): ConfigValues {
  return withSite({ api: { ...SITE.api!, ...changes } })
}

describe('toConfigChanges', () => {
  it('sends nothing when nothing changed', () => {
    expect(hasConfigChanges(toConfigChanges(ORIGINAL, ORIGINAL))).toBe(false)
  })

  it('sends changed job fields', () => {
    const changes = toConfigChanges({ ...ORIGINAL, fields: ['title', 'url'] }, ORIGINAL)

    expect(changes).toEqual({ fields: ['title', 'url'] })
  })

  it('sends only the changed site field', () => {
    expect(toConfigChanges(withSite({ isEnabled: false }), ORIGINAL)).toEqual({
      sites: { upwork: { isEnabled: false } },
    })
  })

  it('sends a changed site limit', () => {
    expect(toConfigChanges(withSite({ limit: 9 }), ORIGINAL)).toEqual({
      sites: { upwork: { limit: 9 } },
    })
  })

  it('never sends an emptied site limit', () => {
    expect(toConfigChanges(withSite({ limit: null }), ORIGINAL)).toEqual({})
  })

  it('sends null when the site max age is emptied, for no age cut', () => {
    expect(toConfigChanges(withSite({ maxAgeHours: null }), ORIGINAL)).toEqual({
      sites: { upwork: { maxAgeHours: null } },
    })
  })

  it('sends a changed site filter whole', () => {
    const filter = { ...EMPTY_FILTER, workType: ['remote'] }

    expect(toConfigChanges(withSite({ filter }), ORIGINAL)).toEqual({
      sites: { upwork: { filter } },
    })
  })

  it('sends an emptied site filter as empty lists, never null', () => {
    const original = withSite({ filter: { ...EMPTY_FILTER, location: ['jakarta'] } })

    expect(toConfigChanges(withSite({ filter: EMPTY_FILTER }), original)).toEqual({
      sites: { upwork: { filter: EMPTY_FILTER } },
    })
  })

  it('sends a changed api block whole', () => {
    const api = { ...SITE.api!, delayMin: 4, delayMax: 6 }

    expect(toConfigChanges(withSite({ api }), ORIGINAL)).toEqual({
      sites: { upwork: { api } },
    })
  })

  it('has no global job settings', () => {
    const changes = toConfigChanges(
      { ...withSite({ limit: 9 }), fields: ['title', 'url'] },
      ORIGINAL,
    )

    expect(Object.keys(changes).sort()).toEqual(['fields', 'sites'])
  })
})

describe('toConfigChanges URL template', () => {
  it('never sends a changed URL template, since it is read only', () => {
    const changes = toConfigChanges(withSite({ urlTemplate: 'https://example.com' }), ORIGINAL)

    expect(changes).toEqual({})
  })

  it('leaves the URL template out of other site changes', () => {
    const changes = toConfigChanges(withSite({ urlTemplate: null, isEnabled: false }), ORIGINAL)

    expect(changes).toEqual({ sites: { upwork: { isEnabled: false } } })
  })
})

describe('toApiStatus', () => {
  it('is on when the site API is enabled', () => {
    expect(toApiStatus(SITE)).toBe('on')
  })

  it('is off when the site API is turned off', () => {
    expect(toApiStatus({ ...SITE, api: { ...SITE.api!, isEnabled: false } })).toBe('off')
  })

  it('is none when the site has no API', () => {
    expect(toApiStatus({ ...SITE, api: null })).toBe('none')
  })
})

describe('toApiStatusLabel', () => {
  it('names each API status', () => {
    expect(toApiStatusLabel('on')).toBe('API on')
    expect(toApiStatusLabel('off')).toBe('API off')
    expect(toApiStatusLabel('none')).toBe('No API')
  })
})

describe('findSiteIssue', () => {
  it('finds nothing when every site is valid', () => {
    expect(findSiteIssue(ORIGINAL)).toBeUndefined()
  })

  it.each([null, 0, SITE_LIMIT_MAX + 1, 2.5])('finds the site with limit %s', (limit) => {
    expect(findSiteIssue(withSite({ limit }))).toEqual({
      siteName: 'upwork',
      field: 'limit',
      message: 'Set a limit from 1 to 200 for upwork',
    })
  })

  it('accepts the highest limit', () => {
    expect(findSiteIssue(withSite({ limit: SITE_LIMIT_MAX }))).toBeUndefined()
  })

  it.each([0, MAX_AGE_HOURS_MAX + 1, 2.5, -3])('finds the site with max age %s', (maxAgeHours) => {
    expect(findSiteIssue(withSite({ maxAgeHours }))).toEqual({
      siteName: 'upwork',
      field: 'maxAgeHours',
      message: 'Set a max job age from 1 to 720 hours for upwork, or leave it empty',
    })
  })

  it.each([null, 1, MAX_AGE_HOURS_MAX])('accepts max age %s', (maxAgeHours) => {
    expect(findSiteIssue(withSite({ maxAgeHours }))).toBeUndefined()
  })

  it('checks every site, not only the first one', () => {
    const values: ConfigValues = {
      ...ORIGINAL,
      sites: [SITE, { ...SITE, name: 'indeed', maxAgeHours: 0 }],
    }

    expect(findSiteIssue(values)?.siteName).toBe('indeed')
  })

  it.each<[number | null, number | null]>([
    [null, null],
    [0, 0],
    [0, DELAY_SECONDS_MAX],
    [2.5, 4],
  ])('accepts delay %s to %s', (delayMin, delayMax) => {
    expect(findSiteIssue(withApi({ delayMin, delayMax }))).toBeUndefined()
  })

  it.each<[number | null, number | null, 'delayMin' | 'delayMax']>([
    [null, 4, 'delayMin'],
    [4, null, 'delayMax'],
  ])('asks for both delay values when only one is set (%s, %s)', (delayMin, delayMax, field) => {
    expect(findSiteIssue(withApi({ delayMin, delayMax }))).toEqual({
      siteName: 'upwork',
      field,
      message: 'Set both delay values for upwork',
    })
  })

  it.each<[number, number, 'delayMin' | 'delayMax']>([
    [-1, 4, 'delayMin'],
    [1, DELAY_SECONDS_MAX + 1, 'delayMax'],
  ])('finds a delay out of range (%s, %s)', (delayMin, delayMax, field) => {
    expect(findSiteIssue(withApi({ delayMin, delayMax }))).toEqual({
      siteName: 'upwork',
      field,
      message: 'Set delays from 0 to 60 seconds for upwork',
    })
  })

  it('finds a min delay above the max delay', () => {
    expect(findSiteIssue(withApi({ delayMin: 8, delayMax: 3 }))).toEqual({
      siteName: 'upwork',
      field: 'delayMin',
      message: 'Set a min delay no higher than the max delay for upwork',
    })
  })

  it('ignores delays on a site without an API', () => {
    expect(findSiteIssue(withSite({ api: null }))).toBeUndefined()
  })
})

describe('toDelaySeconds', () => {
  it('builds the pair from both values', () => {
    expect(toDelaySeconds(4, 6)).toEqual([4, 6])
  })

  it('has no pair when a value is empty', () => {
    expect(toDelaySeconds(null, null)).toBeNull()
    expect(toDelaySeconds(4, null)).toBeNull()
    expect(toDelaySeconds(null, 6)).toBeNull()
  })
})

describe('toJobFieldLabel', () => {
  it.each([
    ['salary_min', 'Salary min'],
    ['company_id', 'Company ID'],
    ['job_id', 'Job ID'],
    ['matched_keyword', 'Matched keyword'],
    ['url', 'URL'],
    ['title', 'Title'],
  ])('turns %s into %s', (field, label) => {
    expect(toJobFieldLabel(field)).toBe(label)
  })
})

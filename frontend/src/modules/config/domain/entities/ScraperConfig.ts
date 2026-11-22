export interface FilterSetting {
  location: string[]
  employmentType: string[]
  workType: string[]
}

export interface ApiSetting {
  isEnabled: boolean
  delayMin: number | null
  delayMax: number | null
}

export interface SiteSetting {
  name: string
  isEnabled: boolean
  limit: number | null
  maxAgeHours: number | null
  urlTemplate: string | null
  filter: FilterSetting
  api: ApiSetting | null
}

export interface ConfigValues {
  fields: string[]
  sites: SiteSetting[]
}

export interface ConfigSnapshot {
  values: ConfigValues
  version: number
  updatedAt: string
  updatedBy: string
  isStale: boolean
  jobFields: string[]
  mandatoryFields: string[]
  locationOptions: string[]
}

export type SiteChanges = Partial<Omit<SiteSetting, 'name' | 'limit' | 'urlTemplate'>> & {
  limit?: number
}

export interface ConfigChanges {
  fields?: string[]
  sites?: Record<string, SiteChanges>
}

export const EMPTY_FILTER: FilterSetting = { location: [], employmentType: [], workType: [] }

export const SITE_LIMIT_MIN = 1
export const SITE_LIMIT_MAX = 200
export const MAX_AGE_HOURS_MIN = 1
export const MAX_AGE_HOURS_MAX = 720
export const DELAY_SECONDS_MIN = 0
export const DELAY_SECONDS_MAX = 60

export type SiteField = 'limit' | 'maxAgeHours' | 'delayMin' | 'delayMax'

export interface SiteIssue {
  siteName: string
  field: SiteField
  message: string
}

export type ApiStatus = 'on' | 'off' | 'none'

export type SiteToggleField = 'isEnabled' | 'apiEnabled'

export interface SiteToggle {
  siteName: string
  field: SiteToggleField
  isOn: boolean
}

const API_STATUS_LABELS: Record<ApiStatus, string> = {
  on: 'API on',
  off: 'API off',
  none: 'No API',
}

const SITE_FIELDS = ['isEnabled', 'limit', 'maxAgeHours', 'filter', 'api'] as const

export function readSiteToggle(site: SiteSetting, field: SiteToggleField): boolean {
  if (field === 'isEnabled') {
    return site.isEnabled
  }
  if (site.api === null) {
    return false
  }
  return site.api.isEnabled
}

export function setSiteToggle(
  site: SiteSetting,
  field: SiteToggleField,
  isOn: boolean,
): SiteSetting {
  if (field === 'isEnabled') {
    return { ...site, isEnabled: isOn }
  }
  if (site.api === null) {
    return site
  }
  return { ...site, api: { ...site.api, isEnabled: isOn } }
}

export function toSiteToggleChanges(savedSite: SiteSetting, toggle: SiteToggle): ConfigChanges {
  const toggledSite = setSiteToggle(savedSite, toggle.field, toggle.isOn)
  if (toggle.field === 'isEnabled') {
    return { sites: { [toggle.siteName]: { isEnabled: toggle.isOn } } }
  }
  return { sites: { [toggle.siteName]: { api: toggledSite.api } } }
}

export function toApiStatus(site: SiteSetting): ApiStatus {
  if (site.api === null) {
    return 'none'
  }
  if (site.api.isEnabled) {
    return 'on'
  }
  return 'off'
}

export function toApiStatusLabel(status: ApiStatus): string {
  return API_STATUS_LABELS[status]
}

export function isValidSiteLimit(limit: number | null): limit is number {
  return (
    limit !== null && Number.isInteger(limit) && limit >= SITE_LIMIT_MIN && limit <= SITE_LIMIT_MAX
  )
}

function isInRange(value: number, min: number, max: number): boolean {
  return Number.isFinite(value) && value >= min && value <= max
}

function isValidMaxAge(maxAgeHours: number | null): boolean {
  return (
    maxAgeHours === null ||
    (Number.isInteger(maxAgeHours) && isInRange(maxAgeHours, MAX_AGE_HOURS_MIN, MAX_AGE_HOURS_MAX))
  )
}

function isValidDelay(seconds: number): boolean {
  return isInRange(seconds, DELAY_SECONDS_MIN, DELAY_SECONDS_MAX)
}

function toDelayIssue(site: SiteSetting): Omit<SiteIssue, 'siteName'> | null {
  if (site.api === null) {
    return null
  }
  const { delayMin, delayMax } = site.api
  if (delayMin === null && delayMax === null) {
    return null
  }
  if (delayMin === null || delayMax === null) {
    const field = delayMin === null ? 'delayMin' : 'delayMax'
    return { field, message: `Set both delay values for ${site.name}` }
  }
  const rangeMessage = `Set delays from ${DELAY_SECONDS_MIN} to ${DELAY_SECONDS_MAX} seconds for ${site.name}`
  if (!isValidDelay(delayMin)) {
    return { field: 'delayMin', message: rangeMessage }
  }
  if (!isValidDelay(delayMax)) {
    return { field: 'delayMax', message: rangeMessage }
  }
  if (delayMin > delayMax) {
    return {
      field: 'delayMin',
      message: `Set a min delay no higher than the max delay for ${site.name}`,
    }
  }
  return null
}

export function toSiteIssues(site: SiteSetting): SiteIssue[] {
  const limitIssue = isValidSiteLimit(site.limit)
    ? null
    : {
        field: 'limit' as const,
        message: `Set a limit from ${SITE_LIMIT_MIN} to ${SITE_LIMIT_MAX} for ${site.name}`,
      }
  const maxAgeIssue = isValidMaxAge(site.maxAgeHours)
    ? null
    : {
        field: 'maxAgeHours' as const,
        message: `Set a max job age from ${MAX_AGE_HOURS_MIN} to ${MAX_AGE_HOURS_MAX} hours for ${site.name}, or leave it empty`,
      }
  return [limitIssue, maxAgeIssue, toDelayIssue(site)].flatMap((issue) =>
    issue === null ? [] : [{ siteName: site.name, ...issue }],
  )
}

export function findSiteIssue(values: ConfigValues): SiteIssue | undefined {
  return values.sites.flatMap(toSiteIssues)[0]
}

export function toDelaySeconds(min: number | null, max: number | null): [number, number] | null {
  return min === null || max === null ? null : [min, max]
}

/**
 * Keeps only the optional job fields the scraper knows. Always-saved fields are
 * added by the scraper on every scrape, so they are never stored. An empty known
 * list means the scraper did not send one, so nothing is dropped as unknown
 */
export function toPickedFields(
  fields: string[],
  jobFields: string[],
  mandatoryFields: string[],
): string[] {
  const isKnown = (field: string): boolean => jobFields.length === 0 || jobFields.includes(field)
  return fields.filter((field) => isKnown(field) && !mandatoryFields.includes(field))
}

const UPPERCASE_WORDS = new Set(['id', 'url'])

/** Turns a stored field name like company_id into a label like "Company ID" */
export function toJobFieldLabel(field: string): string {
  const words = field
    .split('_')
    .map((word) => (UPPERCASE_WORDS.has(word) ? word.toUpperCase() : word))
  const [first = '', ...rest] = words
  return [first.charAt(0).toUpperCase() + first.slice(1), ...rest].join(' ')
}

export function isSame(first: unknown, second: unknown): boolean {
  return JSON.stringify(first) === JSON.stringify(second)
}

function toSiteChanges(site: SiteSetting, original: SiteSetting | undefined): SiteChanges {
  const isSent = (field: (typeof SITE_FIELDS)[number]): boolean =>
    !isSame(site[field], original?.[field]) && !(field === 'limit' && site.limit === null)
  const changed = SITE_FIELDS.filter(isSent)
  return Object.fromEntries(changed.map((field) => [field, site[field]])) as SiteChanges
}

function toSitesChanges(values: ConfigValues, original: ConfigValues): Record<string, SiteChanges> {
  const entries = values.sites.map((site): [string, SiteChanges] => [
    site.name,
    toSiteChanges(
      site,
      original.sites.find((candidate) => candidate.name === site.name),
    ),
  ])
  return Object.fromEntries(entries.filter(([, changes]) => Object.keys(changes).length > 0))
}

export function toConfigChanges(values: ConfigValues, original: ConfigValues): ConfigChanges {
  const sites = toSitesChanges(values, original)
  return {
    ...(isSame(values.fields, original.fields) ? {} : { fields: values.fields }),
    ...(Object.keys(sites).length > 0 ? { sites } : {}),
  }
}

export function hasConfigChanges(changes: ConfigChanges): boolean {
  return Object.keys(changes).length > 0
}

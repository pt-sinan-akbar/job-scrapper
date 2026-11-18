import type {
  ApiSetting,
  ConfigChanges,
  ConfigSnapshot,
  FilterSetting,
  LocationOption,
  SiteChanges,
  SiteSetting,
} from '@/modules/config/domain/entities/ScraperConfig'
import { toDelaySeconds, toPickedFields } from '@/modules/config/domain/entities/ScraperConfig'

export interface FilterModel {
  location?: string[]
  employment_type?: string[]
  work_type?: string[]
}

export interface ApiModel {
  enabled?: boolean
  locations?: string[]
  country_wide?: boolean
  delay_seconds?: [number, number] | null
}

export interface SiteModel {
  name: string
  enabled: boolean
  limit: number
  max_age_hours: number | null
  filter: FilterModel
  fields: string[] | null
  api: ApiModel | null
}

export interface LocationOptionModel {
  label: string
  value: string
}

export interface ConfigModel {
  values: {
    default_fields: string[]
    sites: SiteModel[]
  }
  version: number
  updated_at: string
  updated_by: string
  is_stale: boolean
  job_fields: string[]
  mandatory_fields: string[]
  location_options?: Record<string, LocationOptionModel[]>
}

export interface FilterChangesModel {
  location: string[]
  employment_type: string[]
  work_type: string[]
}

export interface SiteChangesModel {
  enabled?: boolean
  limit?: number
  max_age_hours?: number | null
  filter?: FilterChangesModel
  fields?: string[] | null
  api?: ApiModel | null
}

export interface ConfigChangesModel {
  default_fields?: string[]
  sites?: Record<string, SiteChangesModel>
}

function toFilterSetting(model: FilterModel): FilterSetting {
  return {
    location: model.location ?? [],
    employmentType: model.employment_type ?? [],
    workType: model.work_type ?? [],
  }
}

function toApiSetting(model: ApiModel): ApiSetting {
  return {
    isEnabled: model.enabled ?? true,
    locations: model.locations ?? [],
    isCountryWide: model.country_wide ?? false,
    delayMin: model.delay_seconds?.[0] ?? null,
    delayMax: model.delay_seconds?.[1] ?? null,
  }
}

function toSiteSetting(model: SiteModel, pickFields: (fields: string[]) => string[]): SiteSetting {
  return {
    name: model.name,
    isEnabled: model.enabled,
    limit: model.limit,
    maxAgeHours: model.max_age_hours,
    filter: toFilterSetting(model.filter),
    fields: model.fields === null ? null : pickFields(model.fields),
    api: model.api === null ? null : toApiSetting(model.api),
  }
}

function isLocationOption(entry: unknown): entry is LocationOption {
  if (typeof entry !== 'object' || entry === null) {
    return false
  }
  const { label, value } = entry as Partial<LocationOption>
  return typeof label === 'string' && typeof value === 'string'
}

/** Keeps only well-formed city lists, so a bad reply never breaks the page */
function toLocationOptions(model: unknown): Record<string, LocationOption[]> {
  if (typeof model !== 'object' || model === null || Array.isArray(model)) {
    return {}
  }
  const lists = Object.entries(model).filter(([, list]) => Array.isArray(list))
  return Object.fromEntries(
    lists.map(([site, list]) => [
      site,
      (list as unknown[]).filter(isLocationOption).map(({ label, value }) => ({ label, value })),
    ]),
  )
}

export function toConfigSnapshot(model: ConfigModel): ConfigSnapshot {
  const pickFields = (fields: string[]): string[] =>
    toPickedFields(fields, model.job_fields, model.mandatory_fields)
  return {
    values: {
      defaultFields: pickFields(model.values.default_fields),
      sites: model.values.sites.map((site) => toSiteSetting(site, pickFields)),
    },
    version: model.version,
    updatedAt: model.updated_at,
    updatedBy: model.updated_by,
    isStale: model.is_stale,
    jobFields: model.job_fields,
    mandatoryFields: model.mandatory_fields,
    locationOptions: toLocationOptions(model.location_options),
  }
}

function toFilterChangesModel(filter: FilterSetting): FilterChangesModel {
  return {
    location: filter.location,
    employment_type: filter.employmentType,
    work_type: filter.workType,
  }
}

function toApiModel(api: ApiSetting): ApiModel {
  return {
    enabled: api.isEnabled,
    locations: api.locations,
    country_wide: api.isCountryWide,
    delay_seconds: toDelaySeconds(api.delayMin, api.delayMax),
  }
}

function toSiteChangesModel(changes: SiteChanges): SiteChangesModel {
  const { isEnabled, maxAgeHours, filter, api, ...shared } = changes
  return {
    ...shared,
    ...(isEnabled === undefined ? {} : { enabled: isEnabled }),
    ...(maxAgeHours === undefined ? {} : { max_age_hours: maxAgeHours }),
    ...(filter === undefined ? {} : { filter: toFilterChangesModel(filter) }),
    ...(api === undefined ? {} : { api: api === null ? null : toApiModel(api) }),
  }
}

export function toConfigChangesModel(changes: ConfigChanges): ConfigChangesModel {
  const { defaultFields, sites } = changes
  return {
    ...(defaultFields === undefined ? {} : { default_fields: defaultFields }),
    ...(sites === undefined
      ? {}
      : {
          sites: Object.fromEntries(
            Object.entries(sites).map(([name, site]) => [name, toSiteChangesModel(site)]),
          ),
        }),
  }
}

import type {
  ApiSetting,
  ConfigChanges,
  ConfigSnapshot,
  FilterSetting,
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
  delay_seconds?: [number, number] | null
}

export interface SiteModel {
  name: string
  enabled: boolean
  limit: number
  max_age_hours: number | null
  filter: FilterModel
  api: ApiModel | null
  url_template?: string | null
}

export interface ConfigModel {
  values: {
    fields: string[]
    sites: SiteModel[]
  }
  version: number
  updated_at: string
  updated_by: string
  is_stale: boolean
  job_fields: string[]
  mandatory_fields: string[]
  location_options?: string[]
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
  api?: ApiModel | null
}

export interface ConfigChangesModel {
  fields?: string[]
  sites?: Record<string, SiteChangesModel>
}

function toLocationKey(location: string): string {
  return location.toLowerCase()
}

function findLocationLabel(savedLocation: string, locationOptions: string[]): string | undefined {
  const savedKey = toLocationKey(savedLocation)
  return locationOptions.find((option) => toLocationKey(option) === savedKey)
}

function toPickedLocations(savedLocations: string[], locationOptions: string[]): string[] {
  if (locationOptions.length === 0) {
    return savedLocations
  }
  const labels = savedLocations.map((savedLocation) =>
    findLocationLabel(savedLocation, locationOptions),
  )
  const matchedLabels = labels.filter((label) => label !== undefined)
  return [...new Set(matchedLabels)]
}

function toFilterSetting(model: FilterModel, locationOptions: string[]): FilterSetting {
  return {
    location: toPickedLocations(model.location ?? [], locationOptions),
    employmentType: model.employment_type ?? [],
    workType: model.work_type ?? [],
  }
}

function toApiSetting(model: ApiModel): ApiSetting {
  return {
    isEnabled: model.enabled ?? true,
    delayMin: model.delay_seconds?.[0] ?? null,
    delayMax: model.delay_seconds?.[1] ?? null,
  }
}

function toSiteSetting(model: SiteModel, locationOptions: string[]): SiteSetting {
  return {
    name: model.name,
    isEnabled: model.enabled,
    limit: model.limit,
    maxAgeHours: model.max_age_hours,
    urlTemplate: model.url_template ?? null,
    filter: toFilterSetting(model.filter, locationOptions),
    api: model.api === null ? null : toApiSetting(model.api),
  }
}

function isLocationLabel(entry: unknown): entry is string {
  return typeof entry === 'string'
}

function toLocationOptions(model: unknown): string[] {
  if (!Array.isArray(model)) {
    return []
  }
  return model.filter(isLocationLabel)
}

export function toConfigSnapshot(model: ConfigModel): ConfigSnapshot {
  const locationOptions = toLocationOptions(model.location_options)
  return {
    values: {
      fields: toPickedFields(model.values.fields, model.job_fields, model.mandatory_fields),
      sites: model.values.sites.map((site) => toSiteSetting(site, locationOptions)),
    },
    version: model.version,
    updatedAt: model.updated_at,
    updatedBy: model.updated_by,
    isStale: model.is_stale,
    jobFields: model.job_fields,
    mandatoryFields: model.mandatory_fields,
    locationOptions,
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
  const { fields, sites } = changes
  return {
    ...(fields === undefined ? {} : { fields }),
    ...(sites === undefined
      ? {}
      : {
          sites: Object.fromEntries(
            Object.entries(sites).map(([name, site]) => [name, toSiteChangesModel(site)]),
          ),
        }),
  }
}

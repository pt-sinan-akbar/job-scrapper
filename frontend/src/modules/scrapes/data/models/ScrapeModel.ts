import type {
  JsonObject,
  ScrapeDetail,
  ScrapeDiscordStatus,
  ScrapeFailure,
  ScrapeJob,
  ScrapeOptions,
  ScrapeRecord,
  ScrapeStatus,
} from '@/modules/scrapes/domain/entities/Scrape'

export interface ScrapeRecordModel {
  id: string
  status: ScrapeStatus
  keywords: string[]
  sites: string[]
  started_at: string
  finished_at: string | null
  job_count: number
  error_count: number
  error: string | null
  discord_status?: ScrapeDiscordStatus | null
  discord_sent?: number
  discord_failed?: number
  discord_error?: string | null
}

export interface ScrapeFailureModel {
  keyword: string
  site: string
  reason?: string | null
}

export interface ScrapeDetailModel {
  record: ScrapeRecordModel
  jobs: unknown[]
  failures: ScrapeFailureModel[]
}

export interface ScrapeOptionsModel {
  sites: { name: string; enabled: boolean }[]
  is_stale: boolean
}

export function toScrapeRecord(model: ScrapeRecordModel): ScrapeRecord {
  return {
    id: model.id,
    status: model.status,
    keywords: model.keywords,
    sites: model.sites,
    startedAt: model.started_at,
    finishedAt: model.finished_at,
    jobCount: model.job_count,
    errorCount: model.error_count,
    error: model.error,
    discordStatus: model.discord_status ?? null,
    discordSent: model.discord_sent ?? 0,
    discordFailed: model.discord_failed ?? 0,
    discordError: model.discord_error ?? null,
  }
}

const WEB_URL = /^https?:\/\//i

function isPlainObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function toText(value: unknown): string | null {
  if (typeof value === 'string') {
    return value.trim() === '' ? null : value
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value)
  }
  return null
}

function toWebUrl(value: unknown): string | null {
  const url = toText(value)
  return url !== null && WEB_URL.test(url) ? url : null
}

function toScrapeJob(model: JsonObject): ScrapeJob {
  return {
    site: toText(model.site),
    matchedKeyword: toText(model.matched_keyword),
    title: toText(model.title),
    company: toText(model.company),
    location: toText(model.location),
    url: toWebUrl(model.url),
    postedAt: toText(model.posted_at),
    salary: toText(model.salary),
    workType: toText(model.work_type),
    employmentType: toText(model.employment_type),
    experienceLevel: toText(model.experience_level),
    description: toText(model.requirements),
    json: model,
  }
}

function toScrapeJobs(entries: unknown): ScrapeJob[] {
  if (!Array.isArray(entries)) {
    return []
  }
  return entries.filter(isPlainObject).map(toScrapeJob)
}

function toScrapeFailure(model: ScrapeFailureModel): ScrapeFailure {
  return { keyword: model.keyword, site: model.site, reason: model.reason ?? null }
}

export function toScrapeDetail(model: ScrapeDetailModel): ScrapeDetail {
  return {
    record: toScrapeRecord(model.record),
    jobs: toScrapeJobs(model.jobs),
    failures: model.failures.map(toScrapeFailure),
  }
}

export function toScrapeOptions(model: ScrapeOptionsModel): ScrapeOptions {
  return {
    sites: model.sites.map((site) => ({ name: site.name, isEnabled: site.enabled })),
    isStale: model.is_stale,
  }
}

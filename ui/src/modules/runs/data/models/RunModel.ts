import type {
  JsonObject,
  RunDetail,
  RunDiscordStatus,
  RunFailure,
  RunJob,
  RunOptions,
  RunRecord,
  RunStatus,
} from '@/modules/runs/domain/entities/Run'

export interface RunRecordModel {
  id: string
  status: RunStatus
  keywords: string[]
  sites: string[]
  started_at: string
  finished_at: string | null
  job_count: number
  error_count: number
  error: string | null
  discord_status?: RunDiscordStatus | null
  discord_sent?: number
  discord_failed?: number
  discord_error?: string | null
}

export interface RunFailureModel {
  keyword: string
  site: string
  reason?: string | null
}

export interface RunDetailModel {
  record: RunRecordModel
  jobs: unknown[]
  failures: RunFailureModel[]
}

export interface RunOptionsModel {
  sites: { name: string; enabled: boolean }[]
  is_stale: boolean
}

export function toRunRecord(model: RunRecordModel): RunRecord {
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

function toRunJob(model: JsonObject): RunJob {
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

function toRunJobs(entries: unknown): RunJob[] {
  if (!Array.isArray(entries)) {
    return []
  }
  return entries.filter(isPlainObject).map(toRunJob)
}

function toRunFailure(model: RunFailureModel): RunFailure {
  return { keyword: model.keyword, site: model.site, reason: model.reason ?? null }
}

export function toRunDetail(model: RunDetailModel): RunDetail {
  return {
    record: toRunRecord(model.record),
    jobs: toRunJobs(model.jobs),
    failures: model.failures.map(toRunFailure),
  }
}

export function toRunOptions(model: RunOptionsModel): RunOptions {
  return {
    sites: model.sites.map((site) => ({ name: site.name, isEnabled: site.enabled })),
    isStale: model.is_stale,
  }
}

import type {
  RunDiscordStatus,
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

export interface RunOptionsModel {
  keywords: string[]
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

export function toRunOptions(model: RunOptionsModel): RunOptions {
  return {
    keywords: model.keywords,
    sites: model.sites.map((site) => ({ name: site.name, isEnabled: site.enabled })),
    isStale: model.is_stale,
  }
}

export type RunStatus = 'running' | 'succeeded' | 'partial' | 'failed'

export type RunDiscordStatus = 'sending' | 'sent' | 'partial' | 'failed'

export interface RunRecord {
  id: string
  status: RunStatus
  keywords: string[]
  sites: string[]
  startedAt: string
  finishedAt: string | null
  jobCount: number
  errorCount: number
  error: string | null
  discordStatus: RunDiscordStatus | null
  discordSent: number
  discordFailed: number
  discordError: string | null
}

export interface RunJob {
  site: string | null
  matchedKeyword: string | null
  title: string | null
  company: string | null
  location: string | null
  url: string | null
  postedAt: string | null
  salary: string | null
  workType: string | null
  employmentType: string | null
  experienceLevel: string | null
  description: string | null
  json: JsonObject
}

export interface RunFailure {
  keyword: string
  site: string
  reason: string | null
}

export type JsonValue = string | number | boolean | null | JsonValue[] | JsonObject

export interface JsonObject {
  [key: string]: JsonValue
}

export interface RunDetail {
  record: RunRecord
  jobs: RunJob[]
  failures: RunFailure[]
}

export interface SiteOption {
  name: string
  isEnabled: boolean
}

export interface RunOptions {
  sites: SiteOption[]
  isStale: boolean
}

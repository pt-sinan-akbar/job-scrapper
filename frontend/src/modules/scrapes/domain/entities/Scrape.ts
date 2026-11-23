export const MAX_KEYWORDS = 10

export type ScrapeStatus = 'running' | 'succeeded' | 'partial' | 'failed'

export type ScrapeDiscordStatus = 'sending' | 'sent' | 'partial' | 'failed'

export interface ScrapeRecord {
  id: string
  status: ScrapeStatus
  keywords: string[]
  sites: string[]
  startedAt: string
  finishedAt: string | null
  jobCount: number
  errorCount: number
  error: string | null
  discordStatus: ScrapeDiscordStatus | null
  discordSent: number
  discordFailed: number
  discordError: string | null
}

export interface ScrapeJob {
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

export interface ScrapeFailure {
  keyword: string
  site: string
  reason: string | null
}

export type JsonValue = string | number | boolean | null | JsonValue[] | JsonObject

export interface JsonObject {
  [key: string]: JsonValue
}

export interface ScrapeDetail {
  record: ScrapeRecord
  jobs: ScrapeJob[]
  failures: ScrapeFailure[]
}

export interface SiteOption {
  name: string
  isEnabled: boolean
}

export interface ScrapeOptions {
  sites: SiteOption[]
  isStale: boolean
}

export function isSendableToDiscord(record: ScrapeRecord | null): boolean {
  if (record === null) {
    return false
  }
  return record.status === 'succeeded' || record.status === 'partial'
}

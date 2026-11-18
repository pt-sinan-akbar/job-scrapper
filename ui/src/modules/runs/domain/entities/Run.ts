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

export interface SiteOption {
  name: string
  isEnabled: boolean
}

export interface RunOptions {
  keywords: string[]
  sites: SiteOption[]
  isStale: boolean
}

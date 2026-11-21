import type { ScrapeRecord } from '@/modules/scrapes/domain/entities/Scrape'

export type ScrapeToastKind = 'success' | 'warning' | 'error'

export interface ScrapeToastView {
  label: string
  toastKind: ScrapeToastKind
}

export function formatJobCount(count: number): string {
  return count === 1 ? '1 job' : `${count} jobs`
}

function formatErrorCount(count: number): string {
  return count === 1 ? '1 error' : `${count} errors`
}

function withReason(label: string, reason: string | null): string {
  return reason === null ? label : `${label}: ${reason}`
}

export function toScrapeEndView(record: ScrapeRecord): ScrapeToastView | null {
  switch (record.status) {
    case 'succeeded':
      return {
        label: `Run finished with ${formatJobCount(record.jobCount)}`,
        toastKind: 'success',
      }
    case 'partial':
      return {
        label: `Run finished with ${formatJobCount(record.jobCount)} and ${formatErrorCount(record.errorCount)}`,
        toastKind: 'warning',
      }
    case 'failed':
      return { label: withReason('Run failed', record.error), toastKind: 'error' }
    default:
      return null
  }
}

export function toDiscordStatusView(record: ScrapeRecord): ScrapeToastView | null {
  switch (record.discordStatus) {
    case 'sent':
      return { label: `Sent ${record.discordSent} to Discord`, toastKind: 'success' }
    case 'partial':
      return {
        label: `Sent ${record.discordSent}, failed ${record.discordFailed} on Discord`,
        toastKind: 'warning',
      }
    case 'failed':
      return { label: withReason('Discord failed', record.discordError), toastKind: 'error' }
    default:
      return null
  }
}

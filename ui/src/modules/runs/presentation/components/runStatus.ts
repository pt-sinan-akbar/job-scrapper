import type { RunRecord } from '@/modules/runs/domain/entities/Run'

export type RunToastKind = 'success' | 'warning' | 'error'

export interface RunToastView {
  label: string
  toastKind: RunToastKind
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

export function toRunEndView(record: RunRecord): RunToastView | null {
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

export function toDiscordStatusView(record: RunRecord): RunToastView | null {
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

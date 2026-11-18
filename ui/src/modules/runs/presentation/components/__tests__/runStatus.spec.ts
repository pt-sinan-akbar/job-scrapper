import { describe, expect, it } from 'vitest'
import type { RunRecord } from '@/modules/runs/domain/entities/Run'
import { toDiscordStatusView, toRunEndView } from '@/modules/runs/presentation/components/runStatus'

function makeRecord(overrides: Partial<RunRecord> = {}): RunRecord {
  return {
    id: 'run-1',
    status: 'succeeded',
    keywords: ['django'],
    sites: ['upwork'],
    startedAt: '2026-11-01T10:00:00+00:00',
    finishedAt: null,
    jobCount: 0,
    errorCount: 0,
    error: null,
    discordStatus: null,
    discordSent: 0,
    discordFailed: 0,
    discordError: null,
    ...overrides,
  }
}

describe('toRunEndView', () => {
  it('shows nothing while the run is still going', () => {
    expect(toRunEndView(makeRecord({ status: 'running' }))).toBeNull()
  })

  it('says how many jobs a finished run found', () => {
    expect(toRunEndView(makeRecord({ jobCount: 4 }))).toEqual({
      label: 'Run finished with 4 jobs',
      toastKind: 'success',
    })
  })

  it('uses the singular for one job', () => {
    expect(toRunEndView(makeRecord({ jobCount: 1 }))?.label).toBe('Run finished with 1 job')
  })

  it('warns about errors in a partial run', () => {
    expect(toRunEndView(makeRecord({ status: 'partial', jobCount: 3, errorCount: 2 }))).toEqual({
      label: 'Run finished with 3 jobs and 2 errors',
      toastKind: 'warning',
    })
  })

  it('says why a run failed', () => {
    expect(toRunEndView(makeRecord({ status: 'failed', error: 'Scraper crashed' }))).toEqual({
      label: 'Run failed: Scraper crashed',
      toastKind: 'error',
    })
  })

  it('says the run failed when there is no reason', () => {
    expect(toRunEndView(makeRecord({ status: 'failed' }))).toEqual({
      label: 'Run failed',
      toastKind: 'error',
    })
  })
})

describe('toDiscordStatusView', () => {
  it('shows nothing when there was no send', () => {
    expect(toDiscordStatusView(makeRecord())).toBeNull()
  })

  it('shows nothing while the send is still going', () => {
    expect(toDiscordStatusView(makeRecord({ discordStatus: 'sending' }))).toBeNull()
  })

  it('says how many were sent', () => {
    expect(toDiscordStatusView(makeRecord({ discordStatus: 'sent', discordSent: 5 }))).toEqual({
      label: 'Sent 5 to Discord',
      toastKind: 'success',
    })
  })

  it('says how many were sent and failed', () => {
    const view = toDiscordStatusView(
      makeRecord({ discordStatus: 'partial', discordSent: 4, discordFailed: 2 }),
    )

    expect(view).toEqual({
      label: 'Sent 4, failed 2 on Discord',
      toastKind: 'warning',
    })
  })

  it('says why Discord failed', () => {
    const view = toDiscordStatusView(
      makeRecord({ discordStatus: 'failed', discordError: 'Missing access' }),
    )

    expect(view).toEqual({
      label: 'Discord failed: Missing access',
      toastKind: 'error',
    })
  })

  it('says Discord failed when there is no reason', () => {
    expect(toDiscordStatusView(makeRecord({ discordStatus: 'failed' }))).toEqual({
      label: 'Discord failed',
      toastKind: 'error',
    })
  })
})

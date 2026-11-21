import { describe, expect, it } from 'vitest'
import type { ScrapeRecord } from '@/modules/scrapes/domain/entities/Scrape'
import {
  toDiscordStatusView,
  toScrapeEndView,
} from '@/modules/scrapes/presentation/components/scrapeStatus'

function makeRecord(overrides: Partial<ScrapeRecord> = {}): ScrapeRecord {
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

describe('toScrapeEndView', () => {
  it('shows nothing while the scrape is still going', () => {
    expect(toScrapeEndView(makeRecord({ status: 'running' }))).toBeNull()
  })

  it('says how many jobs a finished scrape found', () => {
    expect(toScrapeEndView(makeRecord({ jobCount: 4 }))).toEqual({
      label: 'Run finished with 4 jobs',
      toastKind: 'success',
    })
  })

  it('uses the singular for one job', () => {
    expect(toScrapeEndView(makeRecord({ jobCount: 1 }))?.label).toBe('Run finished with 1 job')
  })

  it('warns about errors in a partial scrape', () => {
    expect(toScrapeEndView(makeRecord({ status: 'partial', jobCount: 3, errorCount: 2 }))).toEqual({
      label: 'Run finished with 3 jobs and 2 errors',
      toastKind: 'warning',
    })
  })

  it('says why a scrape failed', () => {
    expect(toScrapeEndView(makeRecord({ status: 'failed', error: 'Scraper crashed' }))).toEqual({
      label: 'Run failed: Scraper crashed',
      toastKind: 'error',
    })
  })

  it('says the scrape failed when there is no reason', () => {
    expect(toScrapeEndView(makeRecord({ status: 'failed' }))).toEqual({
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

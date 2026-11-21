import { describe, expect, it } from 'vitest'
import { isSendableToDiscord, type ScrapeRecord } from '@/modules/scrapes/domain/entities/Scrape'

function record(status: ScrapeRecord['status']): ScrapeRecord {
  return {
    id: 'run-1',
    status,
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
  }
}

describe('isSendableToDiscord', () => {
  it.each(['succeeded', 'partial'] as const)('is true for a %s scrape', (status) => {
    expect(isSendableToDiscord(record(status))).toBe(true)
  })

  it.each(['running', 'failed'] as const)('is false for a %s scrape', (status) => {
    expect(isSendableToDiscord(record(status))).toBe(false)
  })

  it('is false when there is no scrape', () => {
    expect(isSendableToDiscord(null)).toBe(false)
  })

  it('is true for a finished scrape with zero jobs', () => {
    expect(isSendableToDiscord({ ...record('succeeded'), jobCount: 0 })).toBe(true)
  })
})

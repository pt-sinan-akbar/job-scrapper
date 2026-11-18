import { describe, expect, it } from 'vitest'
import { toRunRecord, type RunRecordModel } from '@/modules/runs/data/models/RunModel'

const MODEL: RunRecordModel = {
  id: 'run-1',
  status: 'partial',
  keywords: ['django'],
  sites: ['upwork'],
  started_at: '2026-11-01T10:00:00+00:00',
  finished_at: '2026-11-01T10:01:00+00:00',
  job_count: 1,
  error_count: 1,
  error: null,
  discord_status: 'partial',
  discord_sent: 3,
  discord_failed: 1,
  discord_error: 'Missing access',
}

describe('toRunRecord', () => {
  it('maps API fields', () => {
    const record = toRunRecord(MODEL)

    expect(record.id).toBe('run-1')
    expect(record.status).toBe('partial')
    expect(record.jobCount).toBe(1)
    expect(record.errorCount).toBe(1)
    expect(record.startedAt).toBe('2026-11-01T10:00:00+00:00')
    expect(record.finishedAt).toBe('2026-11-01T10:01:00+00:00')
  })

  it('maps the discord send fields', () => {
    const record = toRunRecord(MODEL)

    expect(record.discordStatus).toBe('partial')
    expect(record.discordSent).toBe(3)
    expect(record.discordFailed).toBe(1)
    expect(record.discordError).toBe('Missing access')
  })

  it('treats missing discord fields as no send', () => {
    const { discord_status, discord_sent, discord_failed, discord_error, ...old } = MODEL
    void [discord_status, discord_sent, discord_failed, discord_error]

    const record = toRunRecord(old)

    expect(record.discordStatus).toBeNull()
    expect(record.discordSent).toBe(0)
    expect(record.discordFailed).toBe(0)
    expect(record.discordError).toBeNull()
  })
})

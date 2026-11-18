import { describe, expect, it } from 'vitest'
import {
  toRunDetail,
  toRunOptions,
  toRunRecord,
  type RunDetailModel,
  type RunOptionsModel,
  type RunRecordModel,
} from '@/modules/runs/data/models/RunModel'

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

describe('toRunDetail', () => {
  const DETAIL_MODEL: RunDetailModel = {
    record: MODEL,
    jobs: [
      {
        site: 'upwork',
        matched_keyword: 'django',
        title: 'Django dev',
        company: 'Acme',
        location: 'Remote',
        url: 'https://example.com/1',
        posted_at: '2026-11-01',
      },
    ],
    failures: [{ keyword: 'django', site: 'indeed', reason: 'Blocked' }],
    payloads: [{ keyword: 'django', site: 'upwork', raw: { items: [1] }, filtered: { count: 1 } }],
  }

  it('maps the record, jobs, failures and payloads', () => {
    const detail = toRunDetail(DETAIL_MODEL)

    expect(detail.record.id).toBe('run-1')
    expect(detail.jobs).toEqual([
      {
        site: 'upwork',
        matchedKeyword: 'django',
        title: 'Django dev',
        company: 'Acme',
        location: 'Remote',
        url: 'https://example.com/1',
        postedAt: '2026-11-01',
      },
    ])
    expect(detail.failures).toEqual([{ keyword: 'django', site: 'indeed', reason: 'Blocked' }])
    expect(detail.payloads).toEqual([
      { keyword: 'django', site: 'upwork', raw: { items: [1] }, filtered: { count: 1 } },
    ])
  })

  it('turns missing job fields and failure reasons into null', () => {
    const detail = toRunDetail({
      ...DETAIL_MODEL,
      jobs: [{}],
      failures: [{ keyword: 'django', site: 'indeed' }],
    })

    expect(detail.jobs[0]).toEqual({
      site: null,
      matchedKeyword: null,
      title: null,
      company: null,
      location: null,
      url: null,
      postedAt: null,
    })
    expect(detail.failures[0]!.reason).toBeNull()
  })

  it.each([['javascript:alert(1)'], ['ftp://example.com'], ['/relative']])(
    'drops a job url that is not a web link: %s',
    (url) => {
      const detail = toRunDetail({ ...DETAIL_MODEL, jobs: [{ title: 'x', url }] })

      expect(detail.jobs[0]!.url).toBeNull()
    },
  )

  it('keeps an empty detail for a run that is still going', () => {
    const detail = toRunDetail({
      record: { ...MODEL, status: 'running' },
      jobs: [],
      failures: [],
      payloads: [],
    })

    expect(detail.record.status).toBe('running')
    expect(detail.jobs).toEqual([])
    expect(detail.failures).toEqual([])
    expect(detail.payloads).toEqual([])
  })

  it('skips payloads that are not shaped like a payload', () => {
    const detail = toRunDetail({
      ...DETAIL_MODEL,
      payloads: [
        null,
        'text',
        { keyword: 1, site: 'upwork', raw: null, filtered: null },
        { keyword: 'django', site: 2, raw: null, filtered: null },
        { keyword: 'django', site: 'indeed', raw: null, filtered: null },
      ],
    })

    expect(detail.payloads).toEqual([
      { keyword: 'django', site: 'indeed', raw: null, filtered: null },
    ])
  })

  it('keeps a payload whose raw or filtered data is left out', () => {
    const detail = toRunDetail({
      ...DETAIL_MODEL,
      payloads: [
        { keyword: 'django', site: 'upwork', filtered: { count: 1 } },
        { keyword: 'vue', site: 'indeed' },
      ],
    })

    expect(detail.payloads).toEqual([
      { keyword: 'django', site: 'upwork', raw: null, filtered: { count: 1 } },
      { keyword: 'vue', site: 'indeed', raw: null, filtered: null },
    ])
  })

  it('keeps any JSON value as raw or filtered data', () => {
    const detail = toRunDetail({
      ...DETAIL_MODEL,
      payloads: [
        { keyword: 'django', site: 'upwork', raw: [{ id: 1 }], filtered: 'text' },
        { keyword: 'vue', site: 'indeed', raw: 3, filtered: false },
      ],
    })

    expect(detail.payloads).toEqual([
      { keyword: 'django', site: 'upwork', raw: [{ id: 1 }], filtered: 'text' },
      { keyword: 'vue', site: 'indeed', raw: 3, filtered: false },
    ])
  })

  it('treats a missing payload list as empty', () => {
    const { payloads, ...rest } = DETAIL_MODEL
    void payloads

    expect(toRunDetail(rest as RunDetailModel).payloads).toEqual([])
  })
})

describe('toRunOptions', () => {
  const OPTIONS_MODEL: RunOptionsModel = {
    sites: [
      { name: 'upwork', enabled: true },
      { name: 'indeed', enabled: false },
    ],
    is_stale: false,
  }

  it('maps the sites and the stale flag', () => {
    expect(toRunOptions(OPTIONS_MODEL)).toEqual({
      sites: [
        { name: 'upwork', isEnabled: true },
        { name: 'indeed', isEnabled: false },
      ],
      isStale: false,
    })
  })

  it('carries no keywords, even from an older API response', () => {
    const model = { ...OPTIONS_MODEL, keywords: ['django'] } as RunOptionsModel

    expect(toRunOptions(model)).not.toHaveProperty('keywords')
  })
})

import { describe, expect, it } from 'vitest'
import {
  toScrapeDetail,
  toScrapeOptions,
  toScrapeRecord,
  type ScrapeDetailModel,
  type ScrapeOptionsModel,
  type ScrapeRecordModel,
} from '@/modules/scrapes/data/models/ScrapeModel'

const MODEL: ScrapeRecordModel = {
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

describe('toScrapeRecord', () => {
  it('maps API fields', () => {
    const record = toScrapeRecord(MODEL)

    expect(record.id).toBe('run-1')
    expect(record.status).toBe('partial')
    expect(record.jobCount).toBe(1)
    expect(record.errorCount).toBe(1)
    expect(record.startedAt).toBe('2026-11-01T10:00:00+00:00')
    expect(record.finishedAt).toBe('2026-11-01T10:01:00+00:00')
  })

  it('maps the discord send fields', () => {
    const record = toScrapeRecord(MODEL)

    expect(record.discordStatus).toBe('partial')
    expect(record.discordSent).toBe(3)
    expect(record.discordFailed).toBe(1)
    expect(record.discordError).toBe('Missing access')
  })

  it('treats missing discord fields as no send', () => {
    const { discord_status, discord_sent, discord_failed, discord_error, ...old } = MODEL
    void [discord_status, discord_sent, discord_failed, discord_error]

    const record = toScrapeRecord(old)

    expect(record.discordStatus).toBeNull()
    expect(record.discordSent).toBe(0)
    expect(record.discordFailed).toBe(0)
    expect(record.discordError).toBeNull()
  })
})

describe('toScrapeDetail', () => {
  const OLD_JOB = {
    site: 'upwork',
    matched_keyword: 'django',
    title: 'Django dev',
    company: 'Acme',
    location: 'Remote',
    url: 'https://example.com/1',
    posted_at: '2026-11-01',
  }
  const FULL_JOB = {
    ...OLD_JOB,
    salary: 'IDR 10m to 15m',
    salary_min: 10000000,
    salary_max: 15000000,
    posted_date: '2026-11-01T00:00:00+00:00',
    work_type: 'Remote',
    employment_type: 'Full time',
    experience_level: 'Senior',
    job_id: 123,
    company_id: 'acme-1',
    requirements: 'Five years of Django',
    tags: ['python', { name: 'django' }],
  }
  const EMPTY_JOB = {
    site: null,
    matchedKeyword: null,
    title: null,
    company: null,
    location: null,
    url: null,
    postedAt: null,
    salary: null,
    workType: null,
    employmentType: null,
    experienceLevel: null,
    description: null,
  }
  const DETAIL_MODEL: ScrapeDetailModel = {
    record: MODEL,
    jobs: [FULL_JOB],
    failures: [{ keyword: 'django', site: 'indeed', reason: 'Blocked' }],
  }

  it('maps the record, jobs and failures', () => {
    const detail = toScrapeDetail(DETAIL_MODEL)

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
        salary: 'IDR 10m to 15m',
        workType: 'Remote',
        employmentType: 'Full time',
        experienceLevel: 'Senior',
        description: 'Five years of Django',
        json: FULL_JOB,
      },
    ])
    expect(detail.failures).toEqual([{ keyword: 'django', site: 'indeed', reason: 'Blocked' }])
  })

  it('carries no payloads, even from an older API response', () => {
    const model = { ...DETAIL_MODEL, payloads: [{ keyword: 'django' }] } as ScrapeDetailModel

    expect(toScrapeDetail(model)).not.toHaveProperty('payloads')
  })

  it('keeps the job object as the API sent it, with every key and value untouched', () => {
    const detail = toScrapeDetail(DETAIL_MODEL)

    expect(detail.jobs[0]!.json).toBe(FULL_JOB)
    expect(detail.jobs[0]!.json).toEqual({
      site: 'upwork',
      matched_keyword: 'django',
      title: 'Django dev',
      company: 'Acme',
      location: 'Remote',
      url: 'https://example.com/1',
      posted_at: '2026-11-01',
      salary: 'IDR 10m to 15m',
      salary_min: 10000000,
      salary_max: 15000000,
      posted_date: '2026-11-01T00:00:00+00:00',
      work_type: 'Remote',
      employment_type: 'Full time',
      experience_level: 'Senior',
      job_id: 123,
      company_id: 'acme-1',
      requirements: 'Five years of Django',
      tags: ['python', { name: 'django' }],
    })
  })

  it('maps a job stored before the full job object was sent', () => {
    const detail = toScrapeDetail({ ...DETAIL_MODEL, jobs: [OLD_JOB] })

    expect(detail.jobs[0]).toEqual({
      ...EMPTY_JOB,
      site: 'upwork',
      matchedKeyword: 'django',
      title: 'Django dev',
      company: 'Acme',
      location: 'Remote',
      url: 'https://example.com/1',
      postedAt: '2026-11-01',
      json: OLD_JOB,
    })
  })

  it('turns missing job fields and failure reasons into null', () => {
    const detail = toScrapeDetail({
      ...DETAIL_MODEL,
      jobs: [{}],
      failures: [{ keyword: 'django', site: 'indeed' }],
    })

    expect(detail.jobs[0]).toEqual({ ...EMPTY_JOB, json: {} })
    expect(detail.failures[0]!.reason).toBeNull()
  })

  it('turns null job fields into null', () => {
    const job = {
      site: null,
      matched_keyword: null,
      title: null,
      company: null,
      location: null,
      url: null,
      posted_at: null,
      salary: null,
      work_type: null,
      employment_type: null,
      experience_level: null,
      requirements: null,
    }

    const detail = toScrapeDetail({ ...DETAIL_MODEL, jobs: [job] })

    expect(detail.jobs[0]).toEqual({ ...EMPTY_JOB, json: job })
  })

  it('shows numbers as text and drops booleans in the display fields', () => {
    const job = {
      site: 7,
      matched_keyword: 0,
      title: 2026,
      company: true,
      location: false,
      posted_at: 1762000000,
      salary: 1500.5,
      work_type: 1,
      employment_type: 2,
      experience_level: 3,
      requirements: 4,
    }

    const detail = toScrapeDetail({ ...DETAIL_MODEL, jobs: [job] })

    expect(detail.jobs[0]).toEqual({
      site: '7',
      matchedKeyword: '0',
      title: '2026',
      company: null,
      location: null,
      url: null,
      postedAt: '1762000000',
      salary: '1500.5',
      workType: '1',
      employmentType: '2',
      experienceLevel: '3',
      description: '4',
      json: job,
    })
  })

  it('drops objects and arrays from the display fields but keeps them in the json', () => {
    const job = {
      site: ['upwork'],
      matched_keyword: { value: 'django' },
      title: { text: 'Django dev' },
      company: [],
      location: {},
      url: { href: 'https://example.com/1' },
      posted_at: ['2026-11-01'],
      salary: { min: 1, max: 2 },
      work_type: ['Remote'],
      employment_type: {},
      experience_level: [],
      requirements: ['Django'],
    }

    const detail = toScrapeDetail({ ...DETAIL_MODEL, jobs: [job] })

    expect(detail.jobs[0]).toEqual({ ...EMPTY_JOB, json: job })
  })

  it.each([[''], ['   '], ['\n\t']])('turns a blank display string into null: %j', (blank) => {
    const job = {
      site: blank,
      matched_keyword: blank,
      title: blank,
      company: blank,
      location: blank,
      url: blank,
      posted_at: blank,
      salary: blank,
      work_type: blank,
      employment_type: blank,
      experience_level: blank,
      requirements: blank,
    }

    const detail = toScrapeDetail({ ...DETAIL_MODEL, jobs: [job] })

    expect(detail.jobs[0]).toEqual({ ...EMPTY_JOB, json: job })
  })

  it('keeps a display string as it was sent', () => {
    const detail = toScrapeDetail({ ...DETAIL_MODEL, jobs: [{ title: ' Django dev ' }] })

    expect(detail.jobs[0]!.title).toBe(' Django dev ')
  })

  it.each([['javascript:alert(1)'], ['ftp://example.com'], ['/relative'], [42], [true]])(
    'drops a job url that is not a web link: %s',
    (url) => {
      const detail = toScrapeDetail({ ...DETAIL_MODEL, jobs: [{ title: 'x', url }] })

      expect(detail.jobs[0]!.url).toBeNull()
      expect(detail.jobs[0]!.json).toEqual({ title: 'x', url })
    },
  )

  it.each([['http://example.com/1'], ['https://example.com/1'], ['HTTPS://example.com/1']])(
    'keeps a job url that is a web link: %s',
    (url) => {
      const detail = toScrapeDetail({ ...DETAIL_MODEL, jobs: [{ url }] })

      expect(detail.jobs[0]!.url).toBe(url)
    },
  )

  it('skips job entries that are not plain objects without crashing', () => {
    const detail = toScrapeDetail({
      ...DETAIL_MODEL,
      jobs: [null, 'text', 3, true, ['nested'], undefined, OLD_JOB],
    })

    expect(detail.jobs).toHaveLength(1)
    expect(detail.jobs[0]!.json).toBe(OLD_JOB)
  })

  it('treats a missing or malformed job list as empty', () => {
    const { jobs, ...rest } = DETAIL_MODEL
    void jobs

    expect(toScrapeDetail(rest as ScrapeDetailModel).jobs).toEqual([])
    expect(toScrapeDetail({ ...rest, jobs: 'text' } as unknown as ScrapeDetailModel).jobs).toEqual(
      [],
    )
  })

  it('does not change the job object it was given', () => {
    const job = Object.freeze({ ...FULL_JOB })

    expect(() => toScrapeDetail({ ...DETAIL_MODEL, jobs: [job] })).not.toThrow()
  })

  it('keeps an empty detail for a scrape that is still going', () => {
    const detail = toScrapeDetail({
      record: { ...MODEL, status: 'running' },
      jobs: [],
      failures: [],
    })

    expect(detail.record.status).toBe('running')
    expect(detail.jobs).toEqual([])
    expect(detail.failures).toEqual([])
  })
})

describe('toScrapeOptions', () => {
  const OPTIONS_MODEL: ScrapeOptionsModel = {
    sites: [
      { name: 'upwork', enabled: true },
      { name: 'indeed', enabled: false },
    ],
    is_stale: false,
  }

  it('maps the sites and the stale flag', () => {
    expect(toScrapeOptions(OPTIONS_MODEL)).toEqual({
      sites: [
        { name: 'upwork', isEnabled: true },
        { name: 'indeed', isEnabled: false },
      ],
      isStale: false,
    })
  })

  it('carries no keywords, even from an older API response', () => {
    const model = { ...OPTIONS_MODEL, keywords: ['django'] } as ScrapeOptionsModel

    expect(toScrapeOptions(model)).not.toHaveProperty('keywords')
  })
})

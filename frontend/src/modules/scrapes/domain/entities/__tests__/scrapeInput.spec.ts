import { describe, expect, it } from 'vitest'
import type { ScrapeRecord, ScrapeStatus } from '@/modules/scrapes/domain/entities/Scrape'
import {
  isRepeatOfFinishedScrape,
  isSameScrapeInput,
  type ScrapeInput,
} from '@/modules/scrapes/domain/entities/scrapeInput'

function recordOf(status: ScrapeStatus, keywords: string[], sites: string[]): ScrapeRecord {
  return {
    id: 'scrape-1',
    status,
    keywords,
    sites,
    startedAt: '2026-11-01T10:00:00+00:00',
    finishedAt: '2026-11-01T10:01:00+00:00',
    jobCount: 0,
    errorCount: 0,
    error: null,
    discordStatus: null,
    discordSent: 0,
    discordFailed: 0,
    discordError: null,
  }
}

const LATEST = recordOf('succeeded', ['django', 'vue'], ['upwork', 'indeed'])

function inputOf(keywords: string[], sites: string[]): ScrapeInput {
  return { keywords, sites }
}

describe('isSameScrapeInput', () => {
  it('is true for the same keywords and sites', () => {
    expect(isSameScrapeInput(inputOf(['django', 'vue'], ['upwork', 'indeed']), LATEST)).toBe(true)
  })

  it('ignores the order of keywords and sites', () => {
    expect(isSameScrapeInput(inputOf(['vue', 'django'], ['indeed', 'upwork']), LATEST)).toBe(true)
  })

  it('ignores keyword case and surrounding spaces', () => {
    expect(isSameScrapeInput(inputOf([' Django ', 'VUE'], ['upwork', 'indeed']), LATEST)).toBe(true)
  })

  it('ignores a repeated keyword', () => {
    expect(
      isSameScrapeInput(inputOf(['django', 'vue', 'Django'], ['upwork', 'indeed']), LATEST),
    ).toBe(true)
  })

  it('is false when a keyword changed', () => {
    expect(isSameScrapeInput(inputOf(['django', 'react'], ['upwork', 'indeed']), LATEST)).toBe(
      false,
    )
  })

  it('is false when a keyword was added', () => {
    expect(
      isSameScrapeInput(inputOf(['django', 'vue', 'react'], ['upwork', 'indeed']), LATEST),
    ).toBe(false)
  })

  it('is false when a site was removed', () => {
    expect(isSameScrapeInput(inputOf(['django', 'vue'], ['upwork']), LATEST)).toBe(false)
  })

  it('is false when a site was added', () => {
    expect(
      isSameScrapeInput(inputOf(['django', 'vue'], ['upwork', 'indeed', 'linkedin']), LATEST),
    ).toBe(false)
  })
})

describe('isRepeatOfFinishedScrape', () => {
  const sameInput = inputOf(['django', 'vue'], ['upwork', 'indeed'])

  it.each<ScrapeStatus>(['succeeded', 'partial'])(
    'is true for the same input after a %s scrape',
    (status) => {
      const latest = recordOf(status, ['django', 'vue'], ['upwork', 'indeed'])

      expect(isRepeatOfFinishedScrape(sameInput, latest)).toBe(true)
    },
  )

  it.each<ScrapeStatus>(['failed', 'running'])(
    'is false for the same input after a %s scrape',
    (status) => {
      const latest = recordOf(status, ['django', 'vue'], ['upwork', 'indeed'])

      expect(isRepeatOfFinishedScrape(sameInput, latest)).toBe(false)
    },
  )

  it('is false when there is no latest scrape', () => {
    expect(isRepeatOfFinishedScrape(sameInput, null)).toBe(false)
  })

  it('is false for changed input after a succeeded scrape', () => {
    expect(isRepeatOfFinishedScrape(inputOf(['django'], ['upwork', 'indeed']), LATEST)).toBe(false)
  })
})

import type { ScrapeRecord } from '@/modules/scrapes/domain/entities/Scrape'

export interface ScrapeInput {
  keywords: string[]
  sites: string[]
}

export function isRepeatOfFinishedScrape(
  input: ScrapeInput,
  latestScrape: ScrapeRecord | null,
): boolean {
  if (latestScrape === null) {
    return false
  }
  if (!hasScrapeFinishedWithResults(latestScrape)) {
    return false
  }
  return isSameScrapeInput(input, latestScrape)
}

export function isSameScrapeInput(input: ScrapeInput, latestScrape: ScrapeRecord): boolean {
  const inputKeywordKeys = input.keywords.map(toKeywordKey)
  const latestKeywordKeys = latestScrape.keywords.map(toKeywordKey)
  if (!haveSameValues(inputKeywordKeys, latestKeywordKeys)) {
    return false
  }
  return haveSameValues(input.sites, latestScrape.sites)
}

export function toKeywordKey(keyword: string): string {
  return keyword.trim().toLowerCase()
}

function hasScrapeFinishedWithResults(latestScrape: ScrapeRecord): boolean {
  return latestScrape.status === 'succeeded' || latestScrape.status === 'partial'
}

function haveSameValues(firstValues: string[], secondValues: string[]): boolean {
  const firstSet = new Set(firstValues)
  const secondSet = new Set(secondValues)
  if (firstSet.size !== secondSet.size) {
    return false
  }
  for (const value of firstSet) {
    if (!secondSet.has(value)) {
      return false
    }
  }
  return true
}

import type {
  ScrapeDetail,
  ScrapeOptions,
  ScrapeRecord,
} from '@/modules/scrapes/domain/entities/Scrape'

export interface ScrapeRepository {
  getOptions(): Promise<ScrapeOptions>
  getScrape(id: string): Promise<ScrapeDetail>
  getLatestScrape(): Promise<ScrapeDetail | null>
  startScrape(keywords: string[], sites: string[], notifyDiscord: boolean): Promise<ScrapeRecord>
  sendLatestScrapeToDiscord(): Promise<ScrapeRecord>
}

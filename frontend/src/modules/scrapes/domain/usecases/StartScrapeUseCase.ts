import type { ScrapeRecord } from '@/modules/scrapes/domain/entities/Scrape'
import type { ScrapeRepository } from '@/modules/scrapes/domain/repositories/ScrapeRepository'

export class StartScrapeUseCase {
  private readonly repository: ScrapeRepository

  constructor(repository: ScrapeRepository) {
    this.repository = repository
  }

  execute(keywords: string[], sites: string[], notifyDiscord: boolean): Promise<ScrapeRecord> {
    return this.repository.startScrape(keywords, sites, notifyDiscord)
  }
}

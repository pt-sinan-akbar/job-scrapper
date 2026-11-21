import type { ScrapeDetail } from '@/modules/scrapes/domain/entities/Scrape'
import type { ScrapeRepository } from '@/modules/scrapes/domain/repositories/ScrapeRepository'

export class GetLatestScrapeUseCase {
  private readonly repository: ScrapeRepository

  constructor(repository: ScrapeRepository) {
    this.repository = repository
  }

  execute(): Promise<ScrapeDetail | null> {
    return this.repository.getLatestScrape()
  }
}

import type { ScrapeDetail } from '@/modules/scrapes/domain/entities/Scrape'
import type { ScrapeRepository } from '@/modules/scrapes/domain/repositories/ScrapeRepository'

export class GetScrapeUseCase {
  private readonly repository: ScrapeRepository

  constructor(repository: ScrapeRepository) {
    this.repository = repository
  }

  execute(id: string): Promise<ScrapeDetail> {
    return this.repository.getScrape(id)
  }
}

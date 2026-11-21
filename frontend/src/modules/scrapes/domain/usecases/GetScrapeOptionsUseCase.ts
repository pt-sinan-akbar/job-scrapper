import type { ScrapeOptions } from '@/modules/scrapes/domain/entities/Scrape'
import type { ScrapeRepository } from '@/modules/scrapes/domain/repositories/ScrapeRepository'

export class GetScrapeOptionsUseCase {
  private readonly repository: ScrapeRepository

  constructor(repository: ScrapeRepository) {
    this.repository = repository
  }

  execute(): Promise<ScrapeOptions> {
    return this.repository.getOptions()
  }
}

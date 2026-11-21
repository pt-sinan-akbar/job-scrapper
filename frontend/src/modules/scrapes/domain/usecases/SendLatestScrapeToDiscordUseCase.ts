import type { ScrapeRecord } from '@/modules/scrapes/domain/entities/Scrape'
import type { ScrapeRepository } from '@/modules/scrapes/domain/repositories/ScrapeRepository'

export class SendLatestScrapeToDiscordUseCase {
  private readonly repository: ScrapeRepository

  constructor(repository: ScrapeRepository) {
    this.repository = repository
  }

  execute(): Promise<ScrapeRecord> {
    return this.repository.sendLatestScrapeToDiscord()
  }
}

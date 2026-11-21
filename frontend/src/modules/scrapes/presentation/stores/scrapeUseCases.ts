import type { GetLatestScrapeUseCase } from '@/modules/scrapes/domain/usecases/GetLatestScrapeUseCase'
import type { GetScrapeOptionsUseCase } from '@/modules/scrapes/domain/usecases/GetScrapeOptionsUseCase'
import type { GetScrapeUseCase } from '@/modules/scrapes/domain/usecases/GetScrapeUseCase'
import type { SendLatestScrapeToDiscordUseCase } from '@/modules/scrapes/domain/usecases/SendLatestScrapeToDiscordUseCase'
import type { StartScrapeUseCase } from '@/modules/scrapes/domain/usecases/StartScrapeUseCase'

export interface ScrapeUseCases {
  getOptions: Pick<GetScrapeOptionsUseCase, 'execute'>
  getScrape: Pick<GetScrapeUseCase, 'execute'>
  getLatestScrape: Pick<GetLatestScrapeUseCase, 'execute'>
  startScrape: Pick<StartScrapeUseCase, 'execute'>
  sendLatestScrapeToDiscord: Pick<SendLatestScrapeToDiscordUseCase, 'execute'>
}

let useCases: ScrapeUseCases | null = null

export function provideScrapeUseCases(next: ScrapeUseCases): void {
  useCases = next
}

export function requireScrapeUseCases(): ScrapeUseCases {
  if (useCases === null) {
    throw new Error('Scrape use cases are not provided')
  }
  return useCases
}

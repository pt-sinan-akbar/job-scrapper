import { describe, expect, it, vi } from 'vitest'
import type { ScrapeRepository } from '@/modules/scrapes/domain/repositories/ScrapeRepository'
import { SendLatestScrapeToDiscordUseCase } from '@/modules/scrapes/domain/usecases/SendLatestScrapeToDiscordUseCase'

describe('SendLatestScrapeToDiscordUseCase', () => {
  it('asks the repository to send the latest scrape', async () => {
    const repository = {
      sendLatestScrapeToDiscord: vi.fn().mockResolvedValue('record'),
    } as unknown as ScrapeRepository

    await expect(new SendLatestScrapeToDiscordUseCase(repository).execute()).resolves.toBe('record')

    expect(repository.sendLatestScrapeToDiscord).toHaveBeenCalledTimes(1)
  })
})

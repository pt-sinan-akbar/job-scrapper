import { describe, expect, it, vi } from 'vitest'
import type { HttpClient } from '@/core/http/httpClient'
import { ScrapeRemoteDataSource } from '@/modules/scrapes/data/datasources/ScrapeRemoteDataSource'

function makeClient() {
  return {
    get: vi.fn().mockResolvedValue('got'),
    post: vi.fn().mockResolvedValue('posted'),
    put: vi.fn().mockResolvedValue('put'),
  }
}

function makeSource(client: ReturnType<typeof makeClient>): ScrapeRemoteDataSource {
  return new ScrapeRemoteDataSource(client as unknown as HttpClient)
}

describe('ScrapeRemoteDataSource', () => {
  it('posts the latest scrape to Discord without a body', async () => {
    const client = makeClient()

    await expect(makeSource(client).sendLatestScrapeToDiscord()).resolves.toBe('posted')

    expect(client.post).toHaveBeenCalledTimes(1)
    expect(client.post).toHaveBeenCalledWith('/scrapes/latest/discord')
  })
})

import type { ScrapeRemoteDataSource } from '@/modules/scrapes/data/datasources/ScrapeRemoteDataSource'
import {
  toScrapeDetail,
  toScrapeOptions,
  toScrapeRecord,
} from '@/modules/scrapes/data/models/ScrapeModel'
import type {
  ScrapeDetail,
  ScrapeOptions,
  ScrapeRecord,
} from '@/modules/scrapes/domain/entities/Scrape'
import type { ScrapeRepository } from '@/modules/scrapes/domain/repositories/ScrapeRepository'

export class ScrapeRepositoryImpl implements ScrapeRepository {
  private readonly dataSource: ScrapeRemoteDataSource

  constructor(dataSource: ScrapeRemoteDataSource) {
    this.dataSource = dataSource
  }

  async getOptions(): Promise<ScrapeOptions> {
    return toScrapeOptions(await this.dataSource.getOptions())
  }

  async getScrape(id: string): Promise<ScrapeDetail> {
    return toScrapeDetail(await this.dataSource.getScrape(id))
  }

  async getLatestScrape(): Promise<ScrapeDetail | null> {
    const model = await this.dataSource.getLatestScrape()
    return model == null ? null : toScrapeDetail(model)
  }

  async startScrape(
    keywords: string[],
    sites: string[],
    notifyDiscord: boolean,
  ): Promise<ScrapeRecord> {
    return toScrapeRecord(await this.dataSource.startScrape(keywords, sites, notifyDiscord))
  }

  async sendLatestScrapeToDiscord(): Promise<ScrapeRecord> {
    return toScrapeRecord(await this.dataSource.sendLatestScrapeToDiscord())
  }
}

import type { HttpClient } from '@/core/http/httpClient'
import type {
  ScrapeDetailModel,
  ScrapeOptionsModel,
  ScrapeRecordModel,
} from '@/modules/scrapes/data/models/ScrapeModel'

const SITES_PATH = '/sites'
const SCRAPES_PATH = '/scrapes'
const LATEST_SCRAPE_PATH = '/scrapes/latest'
const LATEST_SCRAPE_DISCORD_PATH = '/scrapes/latest/discord'

export class ScrapeRemoteDataSource {
  private readonly client: HttpClient

  constructor(client: HttpClient) {
    this.client = client
  }

  getOptions(): Promise<ScrapeOptionsModel> {
    return this.client.get<ScrapeOptionsModel>(SITES_PATH)
  }

  getScrape(id: string): Promise<ScrapeDetailModel> {
    return this.client.get<ScrapeDetailModel>(`${SCRAPES_PATH}/${encodeURIComponent(id)}`)
  }

  getLatestScrape(): Promise<ScrapeDetailModel | null> {
    return this.client.get<ScrapeDetailModel | null>(LATEST_SCRAPE_PATH)
  }

  startScrape(
    keywords: string[],
    sites: string[],
    notifyDiscord: boolean,
  ): Promise<ScrapeRecordModel> {
    return this.client.post<ScrapeRecordModel>(SCRAPES_PATH, {
      keywords,
      sites,
      notify_discord: notifyDiscord,
    })
  }

  sendLatestScrapeToDiscord(): Promise<ScrapeRecordModel> {
    return this.client.post<ScrapeRecordModel>(LATEST_SCRAPE_DISCORD_PATH)
  }
}

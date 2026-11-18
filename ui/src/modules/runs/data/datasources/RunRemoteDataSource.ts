import type { HttpClient } from '@/core/http/httpClient'
import type {
  RunDetailModel,
  RunOptionsModel,
  RunRecordModel,
} from '@/modules/runs/data/models/RunModel'

const SITES_PATH = '/sites'
const RUNS_PATH = '/runs'
const LATEST_RUN_PATH = '/runs/latest'

export class RunRemoteDataSource {
  private readonly client: HttpClient

  constructor(client: HttpClient) {
    this.client = client
  }

  getOptions(): Promise<RunOptionsModel> {
    return this.client.get<RunOptionsModel>(SITES_PATH)
  }

  getRun(id: string): Promise<RunDetailModel> {
    return this.client.get<RunDetailModel>(`${RUNS_PATH}/${encodeURIComponent(id)}`)
  }

  getLatestRun(): Promise<RunDetailModel | null> {
    return this.client.get<RunDetailModel | null>(LATEST_RUN_PATH)
  }

  startRun(keywords: string[], sites: string[], notifyDiscord: boolean): Promise<RunRecordModel> {
    return this.client.post<RunRecordModel>(RUNS_PATH, {
      keywords,
      sites,
      notify_discord: notifyDiscord,
    })
  }
}

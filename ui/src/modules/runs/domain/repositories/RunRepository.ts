import type { RunDetail, RunOptions, RunRecord } from '@/modules/runs/domain/entities/Run'

export interface RunRepository {
  getOptions(): Promise<RunOptions>
  getRun(id: string): Promise<RunDetail>
  getLatestRun(): Promise<RunDetail | null>
  startRun(keywords: string[], sites: string[], notifyDiscord: boolean): Promise<RunRecord>
}

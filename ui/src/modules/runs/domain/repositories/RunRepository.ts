import type { RunOptions, RunRecord } from '@/modules/runs/domain/entities/Run'

export interface RunRepository {
  getOptions(): Promise<RunOptions>
  getRun(id: string): Promise<RunRecord>
  startRun(keywords: string[], sites: string[], notifyDiscord: boolean): Promise<RunRecord>
}

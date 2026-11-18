import type { RunDetail } from '@/modules/runs/domain/entities/Run'
import type { RunRepository } from '@/modules/runs/domain/repositories/RunRepository'

export class GetLatestRunUseCase {
  private readonly repository: RunRepository

  constructor(repository: RunRepository) {
    this.repository = repository
  }

  execute(): Promise<RunDetail | null> {
    return this.repository.getLatestRun()
  }
}

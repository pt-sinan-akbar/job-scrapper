import type { RunRecord } from '@/modules/runs/domain/entities/Run'
import type { RunRepository } from '@/modules/runs/domain/repositories/RunRepository'

export class GetRunUseCase {
  private readonly repository: RunRepository

  constructor(repository: RunRepository) {
    this.repository = repository
  }

  execute(id: string): Promise<RunRecord> {
    return this.repository.getRun(id)
  }
}

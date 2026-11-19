import type { RunJob } from '@/modules/runs/domain/entities/Run'

const UNTITLED_JOB = 'Untitled job'

export function toJobTitle(job: RunJob | null): string {
  return job?.title?.trim() || UNTITLED_JOB
}

export function toJobJsonLabel(job: RunJob | null): string {
  return `${toJobTitle(job)} JSON`
}

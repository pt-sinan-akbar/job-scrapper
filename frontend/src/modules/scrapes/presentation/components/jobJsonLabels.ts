import type { ScrapeJob } from '@/modules/scrapes/domain/entities/Scrape'

const UNTITLED_JOB = 'Untitled job'

export function toJobTitle(job: ScrapeJob | null): string {
  return job?.title?.trim() || UNTITLED_JOB
}

export function toJobJsonLabel(job: ScrapeJob | null): string {
  return `${toJobTitle(job)} JSON`
}

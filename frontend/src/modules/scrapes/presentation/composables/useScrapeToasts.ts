import { watch } from 'vue'
import { toast } from 'vue-sonner'
import type { ScrapeRecord } from '@/modules/scrapes/domain/entities/Scrape'
import {
  toDiscordStatusView,
  toScrapeEndView,
  type ScrapeToastView,
} from '@/modules/scrapes/presentation/components/scrapeStatus'
import { useScrapeStore } from '@/modules/scrapes/presentation/stores/useScrapeStore'

function showToast(view: ScrapeToastView | null): void {
  if (view !== null) {
    toast[view.toastKind](view.label)
  }
}

function toastOn(
  source: () => ScrapeRecord | null,
  toView: (record: ScrapeRecord) => ScrapeToastView | null,
): void {
  watch(source, (record) => showToast(record === null ? null : toView(record)))
}

export function useScrapeToasts(): void {
  const store = useScrapeStore()
  toastOn(() => store.scrapeOutcome, toScrapeEndView)
  toastOn(() => store.discordOutcome, toDiscordStatusView)
  watch(
    () => store.scrapeError,
    (error) => {
      if (error !== null) {
        toast.error(error.message)
      }
    },
  )
}

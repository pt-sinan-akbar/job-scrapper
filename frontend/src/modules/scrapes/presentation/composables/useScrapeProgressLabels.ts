import { computed, ref, toValue } from 'vue'
import type { ComputedRef, MaybeRefOrGetter } from 'vue'
import { useIntervalFn } from '@vueuse/core'
import type { ScrapeRecord } from '@/modules/scrapes/domain/entities/Scrape'
import { formatElapsedTime } from '@/modules/scrapes/presentation/components/elapsedTime'

const TICK_MS = 1000

export interface ScrapeProgressLabels {
  siteCountLabel: ComputedRef<string>
  keywordLabel: ComputedRef<string>
  elapsedLabel: ComputedRef<string>
}

export function useScrapeProgressLabels(
  record: MaybeRefOrGetter<ScrapeRecord | null>,
): ScrapeProgressLabels {
  const now = ref(Date.now())
  useIntervalFn(() => {
    now.value = Date.now()
  }, TICK_MS)

  const siteCountLabel = computed(() => buildSiteCountLabel(toValue(record)?.sites.length ?? 0))
  const keywordLabel = computed(() => toValue(record)?.keywords.join(', ') ?? '')
  const elapsedLabel = computed(() => {
    const startedAt = toValue(record)?.startedAt
    if (startedAt === undefined) {
      return formatElapsedTime('', now.value)
    }
    return formatElapsedTime(startedAt, now.value)
  })

  return { siteCountLabel, keywordLabel, elapsedLabel }
}

function buildSiteCountLabel(count: number): string {
  if (count === 1) {
    return '1 site'
  }
  return `${count} sites`
}

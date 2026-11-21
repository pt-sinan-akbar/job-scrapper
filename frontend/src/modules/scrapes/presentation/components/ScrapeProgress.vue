<script setup lang="ts">
import { Radar } from '@lucide/vue'
import type { ScrapeRecord } from '@/modules/scrapes/domain/entities/Scrape'
import { useScrapeProgressLabels } from '@/modules/scrapes/presentation/composables/useScrapeProgressLabels'

const SITE_PING_STAGGER_MS = 200

const props = defineProps<{ record: ScrapeRecord }>()

const { siteCountLabel, keywordLabel, elapsedLabel } = useScrapeProgressLabels(() => props.record)

function buildPingDelay(index: number): { animationDelay: string } {
  return { animationDelay: `${index * SITE_PING_STAGGER_MS}ms` }
}
</script>

<template>
  <div
    data-slot="scrape-progress"
    class="flex flex-col gap-4 rounded-md bg-surface-subtle p-4 sm:p-6"
  >
    <div class="flex items-start justify-between gap-3">
      <div class="flex min-w-0 items-center gap-3">
        <span
          aria-hidden="true"
          class="relative flex size-10 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent"
        >
          <span class="beacon-ping absolute inset-0 rounded-full bg-accent/30" />
          <Radar class="relative size-5" />
        </span>
        <div class="flex min-w-0 flex-col">
          <p data-slot="scrape-progress-title" class="text-shimmer text-subheading">
            Scraping {{ siteCountLabel }}
          </p>
          <p data-slot="scrape-progress-keywords" class="truncate text-body-sm text-ink-muted">
            {{ keywordLabel }}
          </p>
        </div>
      </div>
      <span
        data-slot="scrape-progress-elapsed"
        aria-hidden="true"
        class="shrink-0 font-mono text-code text-ink-muted tabular-nums"
      >
        {{ elapsedLabel }}
      </span>
    </div>

    <div aria-hidden="true" class="h-1 overflow-hidden rounded-full bg-line">
      <div class="progress-slide h-full w-2/5 rounded-full bg-accent" />
    </div>

    <ul class="flex flex-wrap gap-2" aria-label="Sites being scraped">
      <li
        v-for="(site, index) in record.sites"
        :key="site"
        class="inline-flex h-8 items-center gap-2 rounded-full bg-surface px-3 text-caption text-ink"
      >
        <span aria-hidden="true" class="relative flex size-2">
          <span
            class="beacon-ping absolute inset-0 rounded-full bg-accent"
            :style="buildPingDelay(index)"
          />
          <span class="relative size-2 rounded-full bg-accent" />
        </span>
        {{ site }}
      </li>
    </ul>
  </div>
</template>

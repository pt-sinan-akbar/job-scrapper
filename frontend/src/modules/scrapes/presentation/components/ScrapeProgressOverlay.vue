<script setup lang="ts">
import { computed } from 'vue'
import { Radar } from '@lucide/vue'
import type { ScrapeRecord } from '@/modules/scrapes/domain/entities/Scrape'
import { useScrapeProgressLabels } from '@/modules/scrapes/presentation/composables/useScrapeProgressLabels'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/shared/components/ui/dialog'

const RING_DELAYS_MS = [0, 600, 1200] as const
const SITE_PING_STAGGER_MS = 200

const props = defineProps<{ record: ScrapeRecord | null; isHidden: boolean }>()
const emit = defineEmits<{ hide: [] }>()

const isOpen = computed(() => props.record !== null && !props.isHidden)
const { siteCountLabel, keywordLabel, elapsedLabel } = useScrapeProgressLabels(() => props.record)

function hideWhenClosed(isNextOpen: boolean): void {
  if (!isNextOpen) {
    emit('hide')
  }
}

function buildDelay(delayMs: number): { animationDelay: string } {
  return { animationDelay: `${delayMs}ms` }
}
</script>

<template>
  <Dialog :open="isOpen" @update:open="hideWhenClosed">
    <DialogContent
      data-slot="scrape-progress-overlay"
      :show-close-button="false"
      class="inset-0 top-0 h-dvh max-h-none w-full max-w-none translate-y-0 items-center justify-center overflow-y-auto rounded-none bg-surface/95 p-6 backdrop-blur-md data-open:zoom-in-100 data-closed:zoom-out-100"
    >
      <div class="flex w-full max-w-md flex-col items-center gap-8 text-center">
        <div aria-hidden="true" class="relative flex size-32 items-center justify-center">
          <span
            v-for="delayMs in RING_DELAYS_MS"
            :key="delayMs"
            class="beacon-ping absolute inset-4 rounded-full bg-accent/25"
            :style="buildDelay(delayMs)"
          />
          <span
            class="relative flex size-24 items-center justify-center rounded-full bg-accent-soft text-accent"
          >
            <Radar class="size-12 animate-spin [animation-duration:3s]" />
          </span>
        </div>

        <div class="flex flex-col items-center gap-2">
          <DialogTitle data-slot="scrape-overlay-title" class="text-shimmer text-title">
            Scraping {{ siteCountLabel }}
          </DialogTitle>
          <DialogDescription data-slot="scrape-overlay-keywords" class="text-body text-ink-muted">
            {{ keywordLabel }}
          </DialogDescription>
        </div>

        <span
          data-slot="scrape-overlay-elapsed"
          aria-hidden="true"
          class="font-mono text-display text-ink tabular-nums"
        >
          {{ elapsedLabel }}
        </span>

        <div aria-hidden="true" class="h-1.5 w-full overflow-hidden rounded-full bg-line">
          <div class="progress-slide h-full w-2/5 rounded-full bg-accent" />
        </div>

        <ul
          v-if="record"
          class="flex flex-wrap justify-center gap-2"
          aria-label="Sites being scraped"
        >
          <li
            v-for="(site, index) in record.sites"
            :key="site"
            class="inline-flex h-8 items-center gap-2 rounded-full bg-surface-subtle px-3 text-caption text-ink"
          >
            <span aria-hidden="true" class="relative flex size-2">
              <span
                class="beacon-ping absolute inset-0 rounded-full bg-accent"
                :style="buildDelay(index * SITE_PING_STAGGER_MS)"
              />
              <span class="relative size-2 rounded-full bg-accent" />
            </span>
            {{ site }}
          </li>
        </ul>

        <Button data-slot="scrape-overlay-hide" @click="emit('hide')">Keep browsing</Button>
      </div>
    </DialogContent>
  </Dialog>
</template>

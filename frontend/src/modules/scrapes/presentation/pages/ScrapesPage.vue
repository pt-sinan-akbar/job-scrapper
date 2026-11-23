<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import ScrapeConfigSection from '@/modules/config/presentation/components/ScrapeConfigSection.vue'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import { useDiscordSettingsStore } from '@/modules/discord/presentation/stores/useDiscordSettingsStore'
import ScrapeForm from '@/modules/scrapes/presentation/components/ScrapeForm.vue'
import ScrapeProgressOverlay from '@/modules/scrapes/presentation/components/ScrapeProgressOverlay.vue'
import ScrapeResults from '@/modules/scrapes/presentation/components/ScrapeResults.vue'
import { useDeferredScroll } from '@/modules/scrapes/presentation/composables/useDeferredScroll'
import { toNotifyDiscordBlock } from '@/modules/scrapes/presentation/components/notifyDiscordBlock'
import { useScrapeStore } from '@/modules/scrapes/presentation/stores/useScrapeStore'
import PageSection from '@/shared/components/PageSection.vue'
import { Button } from '@/shared/components/ui/button'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { isPendingStatus } from '@/shared/utils/loadStatus'

const CONFIG_ID = 'config'

const route = useRoute()
const store = useScrapeStore()
const configStore = useConfigStore()
const discordSettingsStore = useDiscordSettingsStore()
const hiddenOverlayScrapeId = ref<string | null>(null)
const isOverlayHidden = computed(
  () => store.runningRecord !== null && store.runningRecord.id === hiddenOverlayScrapeId.value,
)
const isFirstLoad = computed(() => isPendingStatus(store.status) && store.options === null)
const notifyDiscordBlock = computed(() =>
  toNotifyDiscordBlock(discordSettingsStore.status, discordSettingsStore.settings),
)
const isResultsVisible = computed(
  () =>
    store.isResultsPending ||
    store.isResultsLost ||
    store.latestScrape !== null ||
    store.latestErrorMessage !== null,
)
const isSettled = computed(() =>
  [store.status, configStore.status, discordSettingsStore.status].every(
    (status) => !isPendingStatus(status),
  ),
)

const startConfigScroll = useDeferredScroll(CONFIG_ID, () => isSettled.value)

onMounted(() => {
  void store.load()
  void store.loadLatest()
  if (discordSettingsStore.status === 'idle') {
    void discordSettingsStore.load()
  }
  if (route.hash === `#${CONFIG_ID}`) {
    startConfigScroll()
  }
})

function hideScrapeOverlay(): void {
  hiddenOverlayScrapeId.value = store.runningRecord?.id ?? null
}
</script>

<template>
  <header class="flex flex-wrap items-start justify-between gap-3">
    <h2 id="scrapes-heading" class="min-w-0 text-title text-ink">Runs</h2>
  </header>

  <div class="flex min-w-0 flex-col gap-6 md:gap-4">
    <p
      v-if="store.options?.isStale"
      role="status"
      class="rounded-md border border-line-strong p-4 text-body-sm text-ink"
    >
      The scraper is busy, so this list may be out of date
    </p>

    <PageSection title="Start a run">
      <div
        v-if="store.status === 'error'"
        role="alert"
        class="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line-strong p-4"
      >
        <div class="flex min-w-0 flex-col">
          <p class="text-body font-semibold text-ink">Could not load runs</p>
          <p v-if="store.errorMessage" class="text-body-sm text-ink-muted">
            {{ store.errorMessage }}
          </p>
        </div>
        <Button size="sm" @click="store.load">Try again</Button>
      </div>
      <div v-if="isFirstLoad" role="status" aria-busy="true" class="flex flex-col gap-4">
        <span class="sr-only">Loading run options</span>
        <Skeleton class="h-10 w-full" />
        <Skeleton class="h-6 w-2/3" />
        <Skeleton class="h-10 w-32" />
      </div>
      <ScrapeForm
        v-else-if="store.options"
        :options="store.options"
        :is-scraping="store.isScraping"
        :discord-block="notifyDiscordBlock"
        :has-unsaved-config="configStore.isDirty"
        :latest-scrape="store.latestScrape?.record ?? null"
        @start="(keywords, sites, notifyDiscord) => store.start(keywords, sites, notifyDiscord)"
      />
    </PageSection>

    <ScrapeResults
      v-if="isResultsVisible"
      :detail="store.latestScrape"
      :is-pending="store.isResultsPending"
      :running-record="store.runningRecord"
      :is-lost="store.isResultsLost"
      :error-message="store.latestErrorMessage"
      @retry="store.loadLatest"
    />

    <ScrapeConfigSection :id="CONFIG_ID" class="scroll-mt-24" />

    <ScrapeProgressOverlay
      :record="store.runningRecord"
      :is-hidden="isOverlayHidden"
      @hide="hideScrapeOverlay"
    />
  </div>
</template>

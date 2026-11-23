<script setup lang="ts">
import { Play } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { MAX_KEYWORDS, type ScrapeOptions } from '@/modules/scrapes/domain/entities/Scrape'
import type { NotifyDiscordBlock } from '@/modules/scrapes/presentation/components/notifyDiscordBlock'
import {
  readNotifyDiscord,
  writeNotifyDiscord,
} from '@/modules/scrapes/presentation/components/notifyDiscordStorage'
import { Button } from '@/shared/components/ui/button'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { parseKeywords } from '@/shared/utils/parseKeywords'

const DISCORD_ROUTE = '/discord'
const CONFIG_ROUTE = { path: '/scrapes', hash: '#config' }
const KEYWORDS_HINT_ID = 'scrape-keywords-hint'

interface DiscordHint {
  text: string
  linksToDiscord: boolean
}

const DISCORD_HINTS: Record<NotifyDiscordBlock, DiscordHint | null> = {
  loading: null,
  'load-failed': { text: 'Could not load Discord settings', linksToDiscord: false },
  'not-configured': { text: 'Save a bot token on the', linksToDiscord: true },
  'no-channel': { text: 'Set a default channel on the', linksToDiscord: true },
}

const props = withDefaults(
  defineProps<{
    options: ScrapeOptions
    isScraping: boolean
    discordBlock?: NotifyDiscordBlock | null
    hasUnsavedConfig?: boolean
  }>(),
  { discordBlock: null, hasUnsavedConfig: false },
)
const emit = defineEmits<{ start: [keywords: string[], sites: string[], notifyDiscord: boolean] }>()

const keywordText = ref('')
const pickedSites = ref<string[]>([])
const shouldNotifyDiscord = ref(readNotifyDiscord())

const keywords = computed(() => parseKeywords(keywordText.value))
const hasTooManyKeywords = computed(() => keywords.value.length > MAX_KEYWORDS)
const canNotifyDiscord = computed(() => props.discordBlock === null)
const discordHint = computed(() =>
  props.discordBlock === null ? null : DISCORD_HINTS[props.discordBlock],
)
const notifyDiscord = computed(() => canNotifyDiscord.value && shouldNotifyDiscord.value)
const canStart = computed(
  () =>
    keywords.value.length > 0 &&
    !hasTooManyKeywords.value &&
    pickedSites.value.length > 0 &&
    !props.isScraping &&
    !props.hasUnsavedConfig,
)

watch(
  () => props.options,
  (options) => {
    pickedSites.value = options.sites.filter((site) => site.isEnabled).map((site) => site.name)
  },
  { immediate: true },
)

function startScrape(): void {
  if (!canStart.value) {
    return
  }
  emit('start', keywords.value, pickedSites.value, notifyDiscord.value)
}

function setNotifyDiscord(isPicked: boolean | 'indeterminate'): void {
  shouldNotifyDiscord.value = isPicked === true
  writeNotifyDiscord(shouldNotifyDiscord.value)
}

function setSite(name: string, isPicked: boolean | 'indeterminate'): void {
  pickedSites.value =
    isPicked === true
      ? [...pickedSites.value, name]
      : pickedSites.value.filter((site) => site !== name)
}
</script>

<template>
  <form class="flex flex-col gap-8" @submit.prevent="startScrape">
    <div class="flex flex-col gap-2">
      <Label for="scrape-keywords" class="sr-only">Keywords, separated by commas</Label>
      <div class="flex flex-col gap-3 sm:flex-row">
        <Input
          id="scrape-keywords"
          v-model="keywordText"
          placeholder="data analyst, python"
          class="sm:flex-1"
          :aria-describedby="hasTooManyKeywords ? KEYWORDS_HINT_ID : undefined"
        />
        <Button type="submit" variant="primary" :disabled="!canStart">
          <Play aria-hidden="true" />
          {{ isScraping ? 'Scrape running' : 'Run scrape' }}
        </Button>
      </div>
      <p
        v-if="hasTooManyKeywords"
        :id="KEYWORDS_HINT_ID"
        class="text-body-sm tabular-nums text-danger"
      >
        {{ keywords.length }} / {{ MAX_KEYWORDS }} keywords
      </p>
      <p v-if="hasUnsavedConfig" class="text-body-sm text-ink-muted">
        <RouterLink :to="CONFIG_ROUTE" class="text-link hover:underline">
          Save or discard config changes first
        </RouterLink>
      </p>
    </div>
    <div
      data-slot="scrape-options"
      class="flex flex-col gap-8 sm:flex-row sm:items-start sm:justify-between sm:gap-6"
    >
      <div class="flex flex-col gap-1">
        <div class="flex items-center gap-3">
          <Checkbox
            id="scrape-notify-discord"
            :model-value="notifyDiscord"
            :disabled="!canNotifyDiscord"
            @update:model-value="setNotifyDiscord"
          />
          <Label for="scrape-notify-discord" class="cursor-pointer">Send to Discord</Label>
        </div>
        <p v-if="discordHint" data-slot="discord-hint" class="text-body-sm text-ink-muted">
          {{ discordHint.text }}
          <RouterLink
            v-if="discordHint.linksToDiscord"
            :to="DISCORD_ROUTE"
            class="text-link hover:underline"
            >Discord page</RouterLink
          >
        </p>
      </div>
      <fieldset
        class="flex min-w-0 flex-col gap-2 border-0 p-0 sm:flex-row sm:items-center sm:gap-6"
      >
        <legend class="sr-only">Sites</legend>
        <div data-slot="site-options" class="flex flex-wrap gap-x-6 gap-y-3 sm:justify-end">
          <div v-for="site in options.sites" :key="site.name" class="flex items-center gap-3">
            <Checkbox
              :id="`site-${site.name}`"
              :model-value="pickedSites.includes(site.name)"
              @update:model-value="setSite(site.name, $event)"
            />
            <Label :for="`site-${site.name}`" class="cursor-pointer">{{ site.name }}</Label>
          </div>
        </div>
      </fieldset>
    </div>
  </form>
</template>

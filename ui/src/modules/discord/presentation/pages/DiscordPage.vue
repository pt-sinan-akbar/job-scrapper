<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { toast } from 'vue-sonner'
import { MAX_MESSAGE_CHARS, toSendSummary } from '@/modules/discord/domain/entities/Discord'
import DiscordMessagePreview from '@/modules/discord/presentation/components/DiscordMessagePreview.vue'
import DiscordSendResults from '@/modules/discord/presentation/components/DiscordSendResults.vue'
import DiscordSettingsSection from '@/modules/discord/presentation/components/DiscordSettingsSection.vue'
import { useDiscordComposeStore } from '@/modules/discord/presentation/stores/useDiscordComposeStore'
import { useDiscordSettingsStore } from '@/modules/discord/presentation/stores/useDiscordSettingsStore'
import PageLoadState from '@/shared/components/PageLoadState.vue'
import PageSection from '@/shared/components/PageSection.vue'
import { Button } from '@/shared/components/ui/button'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { Label } from '@/shared/components/ui/label'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { Textarea } from '@/shared/components/ui/textarea'

const settingsStore = useDiscordSettingsStore()
const compose = useDiscordComposeStore()

const settings = computed(() => settingsStore.settings)
const isConfigured = computed(() => settings.value?.isConfigured === true)
const isComposePending = computed(
  () => compose.channels.length === 0 && compose.status !== 'ready' && compose.status !== 'error',
)
const channelGroups = computed(() => {
  const groups = new Map<string, typeof compose.channels>()
  for (const channel of compose.channels) {
    groups.set(channel.guildName, [...(groups.get(channel.guildName) ?? []), channel])
  }
  return [...groups.entries()]
})

function loadCompose(): Promise<void> {
  return settings.value === null ? Promise.resolve() : compose.load(settings.value)
}

function loadPage(): Promise<void> {
  return settingsStore.load()
}

watch(
  settings,
  () => {
    if (isConfigured.value) {
      void loadCompose()
    }
  },
  { immediate: true },
)

async function send(): Promise<void> {
  const result = await compose.send()
  if (result === null) {
    if (compose.sendError !== null) {
      toast.error(compose.sendError)
    }
    return
  }
  const summary = toSendSummary(result)
  if (result.failed === 0) {
    toast.success(summary)
  } else if (result.sent === 0) {
    toast.error(summary)
  } else {
    toast.warning(summary)
  }
}

onMounted(() => {
  if (settingsStore.status === 'idle') {
    void loadPage()
  }
})
</script>

<template>
  <header class="flex flex-wrap items-start justify-between gap-3">
    <h2 id="discord-heading" class="min-w-0 text-title text-ink">Discord</h2>
  </header>

  <PageLoadState
    v-if="settings === null"
    :is-error="settingsStore.status === 'error'"
    loading-label="Loading Discord"
    error-title="Could not load Discord"
    :error-message="settingsStore.errorMessage"
    @retry="loadPage"
  >
    <div class="flex flex-col gap-6 md:gap-4">
      <Skeleton v-for="index in 2" :key="index" class="h-48 w-full rounded-lg" />
    </div>
  </PageLoadState>

  <p v-else-if="!isConfigured" role="status" class="text-body-sm text-ink-muted">
    Save a bot token below to start sending messages
  </p>

  <PageLoadState
    v-else-if="compose.status === 'error' || isComposePending"
    :is-error="compose.status === 'error'"
    loading-label="Loading channels"
    error-title="Could not load Discord"
    :error-message="compose.errorMessage"
    @retry="loadCompose"
  >
    <div class="flex flex-col gap-6 md:gap-4">
      <Skeleton v-for="index in 2" :key="index" class="h-48 w-full rounded-lg" />
    </div>
  </PageLoadState>

  <form v-else class="flex min-w-0 flex-col gap-6 md:gap-4" @submit.prevent="send">
    <PageSection title="Send a message" data-slot="compose-card">
      <div class="flex flex-col gap-8">
        <div class="flex flex-col gap-8">
          <div class="flex flex-col gap-2">
            <Label for="discord-channel">Channel</Label>
            <Select
              :model-value="compose.channelId ?? undefined"
              :disabled="compose.channels.length === 0"
              @update:model-value="compose.channelId = String($event)"
            >
              <SelectTrigger id="discord-channel">
                <SelectValue placeholder="Pick a channel" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup v-for="[guildName, channels] in channelGroups" :key="guildName">
                  <SelectLabel>{{ guildName }}</SelectLabel>
                  <SelectItem v-for="channel in channels" :key="channel.id" :value="channel.id">
                    # {{ channel.name }}
                  </SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <p v-if="compose.channels.length === 0" class="text-body-sm text-ink-muted">
              The bot cannot see any text channel yet. Invite it to a server first
            </p>
          </div>
          <div v-if="compose.hasMentionUser" class="flex items-center gap-3">
            <Checkbox
              id="discord-mention"
              :model-value="compose.mention"
              @update:model-value="compose.mention = $event === true"
            />
            <Label for="discord-mention" class="cursor-pointer">Mention user</Label>
          </div>
        </div>
        <div
          data-slot="compose-grid"
          class="grid min-w-0 items-start gap-8 md:grid-cols-2 md:gap-6 [&>*]:min-w-0"
        >
          <div class="flex flex-col gap-2">
            <Label for="discord-text">Message</Label>
            <Textarea
              id="discord-text"
              v-model="compose.text"
              placeholder="Write a message"
              aria-describedby="discord-char-count"
            />
            <div class="flex flex-wrap items-center justify-between gap-3">
              <p v-if="compose.isOverLimit" role="alert" class="min-w-0 text-body-sm text-danger">
                A message can have at most {{ MAX_MESSAGE_CHARS }} characters, counting the mention
              </p>
              <p
                id="discord-char-count"
                aria-live="polite"
                :data-over="compose.isOverLimit ? 'true' : undefined"
                :class="[
                  'ml-auto text-body-sm tabular-nums',
                  compose.isOverLimit ? 'font-semibold text-danger' : 'text-ink-muted',
                ]"
              >
                {{ compose.charCount }} / {{ MAX_MESSAGE_CHARS }}
              </p>
            </div>
          </div>
          <div class="flex flex-col gap-2">
            <div class="flex items-center justify-between gap-3">
              <span class="text-body-sm font-semibold text-ink">Preview</span>
              <Button
                type="button"
                size="sm"
                :disabled="!compose.canPreview"
                @click="compose.preview"
              >
                {{ compose.isPreviewing ? 'Previewing' : 'Preview' }}
              </Button>
            </div>
            <p v-if="compose.previewError" role="alert" class="text-body-sm text-danger">
              {{ compose.previewError }}
            </p>
            <DiscordMessagePreview
              v-else-if="compose.previewMessages.length > 0"
              :messages="compose.previewMessages"
            />
            <p v-else class="text-body-sm text-ink-muted">Press Preview to see the messages</p>
          </div>
        </div>
        <div class="flex flex-wrap items-center justify-end gap-3">
          <p v-if="compose.sendError" role="alert" class="mr-auto min-w-0 text-body-sm text-danger">
            {{ compose.sendError }}
          </p>
          <Button type="submit" variant="primary" :disabled="!compose.canSend">
            {{ compose.isSending ? 'Sending' : 'Send' }}
          </Button>
        </div>
      </div>
    </PageSection>

    <DiscordSendResults v-if="compose.sendResult" :result="compose.sendResult" />
  </form>

  <DiscordSettingsSection v-if="settings !== null" />
</template>

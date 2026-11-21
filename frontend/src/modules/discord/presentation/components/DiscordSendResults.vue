<script setup lang="ts">
import {
  toSendSummary,
  type DiscordMessageResult,
  type DiscordSendResult,
} from '@/modules/discord/domain/entities/Discord'
import PageSection from '@/shared/components/PageSection.vue'
import { Badge } from '@/shared/components/ui/badge'

const props = defineProps<{ result: DiscordSendResult }>()

const STATUS_VIEWS = {
  sent: { label: 'Sent', tone: 'accent' },
  failed: { label: 'Failed', tone: 'danger' },
} as const

function toLabel(message: DiscordMessageResult): string {
  if (message.title !== null) {
    return message.title
  }
  if (message.kind === 'file') {
    return 'Jobs file'
  }
  return 'Free text'
}

function toJobCountText(message: DiscordMessageResult): string | null {
  if (message.kind !== 'file') {
    return null
  }
  return message.jobCount === 1 ? '1 job' : `${message.jobCount} jobs`
}
</script>

<template>
  <PageSection
    data-slot="discord-send-results"
    title="Result"
    :description="toSendSummary(props.result)"
  >
    <ul class="flex flex-col gap-3">
      <li
        v-for="message in props.result.results"
        :key="message.index"
        class="flex flex-col gap-1 rounded-md border border-line p-4"
      >
        <span class="flex w-full items-center gap-2">
          <span class="min-w-0 flex-1 truncate text-body font-semibold text-ink">
            {{ toLabel(message) }}
          </span>
          <Badge :tone="STATUS_VIEWS[message.status].tone">
            {{ STATUS_VIEWS[message.status].label }}
          </Badge>
        </span>
        <span
          v-if="toJobCountText(message) !== null"
          data-slot="discord-send-job-count"
          class="text-body-sm text-ink-muted"
        >
          {{ toJobCountText(message) }}
        </span>
        <span v-if="message.error" class="text-body-sm text-danger">{{ message.error }}</span>
      </li>
    </ul>
  </PageSection>
</template>

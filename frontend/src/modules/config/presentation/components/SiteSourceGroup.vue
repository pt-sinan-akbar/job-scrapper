<script setup lang="ts">
import { computed } from 'vue'
import {
  toApiStatus,
  toApiStatusLabel,
  type ApiStatus,
  type SiteSetting,
} from '@/modules/config/domain/entities/ScraperConfig'
import SiteGroup from '@/modules/config/presentation/components/SiteGroup.vue'
import { Badge, type BadgeVariants } from '@/shared/components/ui/badge'
import { Label } from '@/shared/components/ui/label'

const NO_URL_TEMPLATE = 'No URL template'

const API_STATUS_TONES: Record<ApiStatus, BadgeVariants['tone']> = {
  on: 'accent',
  off: 'neutral',
  none: 'neutral',
}

const API_STATUS_CLASSES: Record<ApiStatus, string> = {
  on: '',
  off: 'text-ink-muted',
  none: 'bg-transparent text-ink-muted',
}

const props = defineProps<{
  idPrefix: string
  site: SiteSetting
}>()

const apiStatus = computed(() => toApiStatus(props.site))
</script>

<template>
  <SiteGroup legend="Source">
    <div class="flex min-w-0 flex-col gap-2">
      <Label :id="`${idPrefix}-url-template-label`" as="span">URL template</Label>
      <div
        :id="`${idPrefix}-url-template`"
        role="textbox"
        aria-readonly="true"
        aria-multiline="true"
        tabindex="0"
        :aria-labelledby="`${idPrefix}-url-template-label`"
        class="flex min-h-10 w-full min-w-0 items-center rounded-md border border-line bg-surface-subtle px-3 py-2 text-body-sm outline-none select-text focus-visible:focus-ring"
        :class="site.urlTemplate === null ? 'text-ink-muted' : 'font-mono break-all text-ink'"
      >
        {{ site.urlTemplate ?? NO_URL_TEMPLATE }}
      </div>
    </div>
    <div class="flex flex-col items-start gap-2">
      <Label :id="`${idPrefix}-api-status-label`" as="span">API status</Label>
      <Badge
        :id="`${idPrefix}-api-status`"
        role="status"
        :aria-labelledby="`${idPrefix}-api-status-label`"
        :tone="API_STATUS_TONES[apiStatus]"
        :class="API_STATUS_CLASSES[apiStatus]"
      >
        {{ toApiStatusLabel(apiStatus) }}
      </Badge>
    </div>
  </SiteGroup>
</template>

<script setup lang="ts">
import { nextTick } from 'vue'
import type { SiteSetting, SiteToggle } from '@/modules/config/domain/entities/ScraperConfig'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { cn } from '@/shared/utils/cn'

const PREVIOUS_KEYS = new Set(['ArrowUp', 'ArrowLeft'])
const NEXT_KEYS = new Set(['ArrowDown', 'ArrowRight'])

const props = defineProps<{
  sites: SiteSetting[]
  selectedName: string | null
  panelId: string
}>()

const emit = defineEmits<{
  select: [name: string]
  toggle: [toggle: SiteToggle]
}>()

function toTargetIndex(key: string, index: number): number | null {
  const lastIndex = props.sites.length - 1
  if (PREVIOUS_KEYS.has(key)) {
    return index === 0 ? lastIndex : index - 1
  }
  if (NEXT_KEYS.has(key)) {
    return index === lastIndex ? 0 : index + 1
  }
  if (key === 'Home') {
    return 0
  }
  return key === 'End' ? lastIndex : null
}

function hasModifier(event: KeyboardEvent): boolean {
  return event.altKey || event.ctrlKey || event.metaKey || event.shiftKey
}

async function moveSelection(event: KeyboardEvent, index: number): Promise<void> {
  if (hasModifier(event)) {
    return
  }
  const target = toTargetIndex(event.key, index)
  const site = target === null ? undefined : props.sites[target]
  if (target === null || site === undefined) {
    return
  }
  event.preventDefault()
  const list = (event.currentTarget as HTMLElement).closest('ul')
  emit('select', site.name)
  await nextTick()
  list?.querySelectorAll<HTMLButtonElement>('[data-slot="site-select"]')[target]?.focus()
}
</script>

<template>
  <ul
    aria-label="Sites"
    class="-mx-2 flex min-w-0 gap-2 overflow-x-auto px-2 py-1 md:mx-0 md:flex-col md:gap-1 md:overflow-visible md:p-0"
  >
    <li
      v-for="(site, index) in sites"
      :key="site.name"
      :class="
        cn(
          'flex shrink-0 items-center gap-3 rounded-md border border-line pl-3 transition-colors duration-150 hover:bg-surface-subtle md:border-transparent',
          site.name === selectedName && 'border-line-strong bg-surface-subtle',
        )
      "
    >
      <Checkbox
        :model-value="site.isEnabled"
        :aria-label="`Turn on ${site.name}`"
        @update:model-value="
          emit('toggle', { siteName: site.name, field: 'isEnabled', isOn: $event === true })
        "
      />
      <button
        type="button"
        data-slot="site-select"
        :aria-controls="panelId"
        :aria-current="site.name === selectedName ? 'true' : undefined"
        class="flex min-w-0 flex-1 cursor-pointer items-center rounded-md py-2 pr-3 text-left outline-none focus-visible:focus-ring"
        @click="emit('select', site.name)"
        @keydown="moveSelection($event, index)"
      >
        <span
          data-slot="site-name"
          :class="
            cn(
              'text-body-sm font-semibold',
              site.name === selectedName ? 'text-ink' : 'text-ink-muted',
            )
          "
          >{{ site.name }}</span
        >
      </button>
    </li>
  </ul>
</template>

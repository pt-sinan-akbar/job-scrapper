<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUpRightIcon } from '@lucide/vue'
import type { ScrapeJob } from '@/modules/scrapes/domain/entities/Scrape'
import { toJobTitle } from '@/modules/scrapes/presentation/components/jobJsonLabels'
import ScrapeJobDescription from '@/modules/scrapes/presentation/components/ScrapeJobDescription.vue'
import {
  formatExactTime,
  formatRelativeTime,
} from '@/modules/scrapes/presentation/components/relativeTime'
import { Badge } from '@/shared/components/ui/badge'
import { cn } from '@/shared/utils/cn'

type FactKey = 'salary' | 'workType' | 'employmentType' | 'experienceLevel' | 'matchedKeyword'

interface FactField {
  label: string
  key: FactKey
}

interface Fact {
  label: string
  value: string
}

interface MetaPart {
  key: string
  text: string
  iso: string | null
  exact: string | null
}

const META_SEPARATOR = ' · '
const INTERACTIVE_SELECTOR = 'a, button'
const FACT_FIELDS: readonly FactField[] = [
  { label: 'Salary', key: 'salary' },
  { label: 'Work type', key: 'workType' },
  { label: 'Employment', key: 'employmentType' },
  { label: 'Level', key: 'experienceLevel' },
  { label: 'Keyword', key: 'matchedKeyword' },
]

const props = defineProps<{ job: ScrapeJob; isSelected: boolean }>()
const emit = defineEmits<{ select: [] }>()

const now = new Date()

const title = computed(() => toJobTitle(props.job))

const facts = computed<Fact[]>(() =>
  FACT_FIELDS.flatMap(({ label, key }) => {
    const value = props.job[key]?.trim()
    return value ? [{ label, value }] : []
  }),
)

const postedPart = computed<MetaPart | null>(() => {
  const posted = props.job.postedAt?.trim()
  if (!posted) {
    return null
  }
  const relative = formatRelativeTime(posted, now)
  const exact = formatExactTime(posted)
  if (relative === null || exact === null) {
    return { key: 'posted', text: posted, iso: null, exact: null }
  }
  return { key: 'posted', text: relative, iso: posted, exact }
})

const metaParts = computed<MetaPart[]>(() => {
  const company = props.job.company?.trim()
  const location = props.job.location?.trim()
  return [
    ...(company ? [{ key: 'company', text: company, iso: null, exact: null }] : []),
    ...(location ? [{ key: 'location', text: location, iso: null, exact: null }] : []),
    ...(postedPart.value ? [postedPart.value] : []),
  ]
})

function startedOnControl(event: MouseEvent, card: Element): boolean {
  if (!(event.target instanceof Element)) {
    return false
  }
  const control = event.target.closest(INTERACTIVE_SELECTOR)
  return control !== null && card.contains(control)
}

function isSelectingText(card: Element): boolean {
  const selection = window.getSelection()
  return selection !== null && !selection.isCollapsed && card.contains(selection.anchorNode)
}

function onCardClick(event: MouseEvent): void {
  const card = event.currentTarget
  if (!(card instanceof Element) || startedOnControl(event, card) || isSelectingText(card)) {
    return
  }
  emit('select')
}
</script>

<template>
  <article
    data-slot="job-card"
    :data-selected="isSelected ? 'true' : undefined"
    :class="
      cn(
        '@container relative flex min-w-0 cursor-pointer flex-col gap-3 rounded-lg border py-4 pr-4 pl-5',
        'transition-colors duration-150 ease-out',
        'before:absolute before:inset-y-3 before:left-0 before:w-1 before:origin-center before:rounded-r-full before:bg-accent',
        'before:transition-[transform,opacity] before:duration-200 before:ease-out',
        isSelected
          ? 'border-accent bg-accent-soft before:scale-y-100 before:opacity-100'
          : [
              'border-line bg-surface before:scale-y-0 before:opacity-0',
              'hover:border-line-strong hover:bg-surface-subtle has-focus-visible:border-line-strong',
              '[&:active:not(:has(:is(a,button):active))]:border-accent [&:active:not(:has(:is(a,button):active))]:bg-accent-soft',
            ],
      )
    "
    @click="onCardClick"
  >
    <div class="flex min-w-0 flex-col gap-1">
      <header
        class="grid grid-cols-[minmax(0,1fr)] items-start gap-x-3 gap-y-1 @md:grid-cols-[minmax(0,1fr)_auto]"
      >
        <h4 data-slot="job-title" class="pt-1 text-subheading wrap-break-word text-ink">
          <a
            v-if="job.url"
            :href="job.url"
            target="_blank"
            rel="noopener noreferrer"
            class="rounded-sm text-link underline decoration-transparent underline-offset-4 outline-none transition-colors duration-150 hover:decoration-current focus-visible:focus-ring active:text-accent-hover"
            >{{ title }}&nbsp;<ArrowUpRightIcon
              aria-hidden="true"
              class="inline size-4 align-[-2px]"
            /><span class="sr-only">(opens in new tab)</span></a
          >
          <template v-else>{{ title }}</template>
        </h4>
        <Badge v-if="job.site" data-slot="job-site" class="justify-self-start @md:mt-1">
          {{ job.site }}
        </Badge>
      </header>
      <p v-if="metaParts.length > 0" data-slot="job-meta" class="text-body-sm text-ink-muted">
        <template v-for="(part, index) in metaParts" :key="part.key">
          <span v-if="index > 0">{{ META_SEPARATOR }}</span>
          <time v-if="part.iso && part.exact" :datetime="part.iso" :title="part.exact">{{
            part.text
          }}</time>
          <span v-else>{{ part.text }}</span>
        </template>
      </p>
    </div>
    <dl
      v-if="facts.length > 0"
      data-slot="job-facts"
      class="grid grid-cols-1 gap-x-6 gap-y-1 @lg:grid-cols-2"
    >
      <div v-for="fact in facts" :key="fact.label" class="flex min-w-0 gap-3">
        <dt class="w-28 shrink-0 text-body-sm text-ink-muted">{{ fact.label }}</dt>
        <dd class="min-w-0 text-body-sm font-semibold wrap-break-word text-ink">
          {{ fact.value }}
        </dd>
      </div>
    </dl>
    <ScrapeJobDescription v-if="job.description" :description="job.description" />
  </article>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronDownIcon } from '@lucide/vue'
import type { RunFailure, RunJob } from '@/modules/runs/domain/entities/Run'
import RunJobCard from '@/modules/runs/presentation/components/RunJobCard.vue'
import EmptyState from '@/shared/components/EmptyState.vue'
import { Button } from '@/shared/components/ui/button'
import { cn } from '@/shared/utils/cn'

const props = defineProps<{
  jobs: RunJob[]
  failures: RunFailure[]
  error: string | null
  selectedIndex: number
}>()
const emit = defineEmits<{ select: [index: number] }>()

const SPLIT_CLASS = 'lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]'
const COLLAPSED_JOB_COUNT = 3

const isExpanded = ref(false)

const hiddenJobCount = computed(() => Math.max(props.jobs.length - COLLAPSED_JOB_COUNT, 0))
const visibleJobs = computed(() => {
  if (isExpanded.value) {
    return props.jobs
  }
  return props.jobs.slice(0, COLLAPSED_JOB_COUNT)
})
const toggleLabel = computed(() => {
  if (isExpanded.value) {
    return 'Show less'
  }
  return `Show ${hiddenJobCount.value} more`
})

watch(
  () => props.jobs,
  () => {
    isExpanded.value = false
  },
)

function toggleExpanded(): void {
  isExpanded.value = !isExpanded.value
}
</script>

<template>
  <div class="flex min-w-0 flex-col gap-8">
    <p
      v-if="error"
      data-slot="run-error"
      class="rounded-md bg-danger-soft p-4 text-body-sm text-danger"
    >
      {{ error }}
    </p>
    <ul
      v-if="failures.length > 0"
      aria-label="Failed sites"
      class="flex flex-col gap-2 rounded-md border border-line p-4 text-body-sm"
    >
      <li
        v-for="(failure, index) in failures"
        :key="`${failure.site}-${failure.keyword}-${index}`"
        data-slot="run-failure"
      >
        <span class="font-semibold text-danger">{{ failure.site }} · {{ failure.keyword }}</span>
        <span v-if="failure.reason" class="text-ink-muted">: {{ failure.reason }}</span>
      </li>
    </ul>
    <EmptyState
      v-if="jobs.length === 0"
      compact
      title="No jobs found"
      hint="Try other keywords or sites"
    />
    <div v-else :class="cn('grid min-w-0 items-start gap-6', $slots.aside && SPLIT_CLASS)">
      <div class="flex min-w-0 flex-col gap-3">
        <ul id="run-job-list" aria-label="Jobs" class="flex w-full min-w-0 flex-col gap-3">
          <li
            v-for="(job, index) in visibleJobs"
            :key="`${job.url ?? ''}-${index}`"
            data-slot="job-row"
          >
            <RunJobCard
              :job="job"
              :is-selected="Boolean($slots.aside) && index === selectedIndex"
              @select="emit('select', index)"
            />
          </li>
        </ul>
        <Button
          v-if="hiddenJobCount > 0"
          data-slot="job-list-toggle"
          aria-controls="run-job-list"
          :aria-expanded="isExpanded"
          class="w-full"
          @click="toggleExpanded"
        >
          {{ toggleLabel }}
          <ChevronDownIcon
            aria-hidden="true"
            :class="cn('transition-transform duration-200 ease-out', isExpanded && 'rotate-180')"
          />
        </Button>
      </div>
      <aside
        v-if="$slots.aside"
        data-slot="job-aside"
        aria-label="Selected job JSON"
        class="relative min-h-96 min-w-0 self-stretch"
      >
        <div class="absolute inset-0">
          <div class="sticky top-20 h-[min(100%,calc(100dvh-6rem))] min-h-0">
            <slot name="aside" />
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

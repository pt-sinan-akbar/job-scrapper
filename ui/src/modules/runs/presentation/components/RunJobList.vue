<script setup lang="ts">
import type { RunFailure, RunJob } from '@/modules/runs/domain/entities/Run'
import RunJobCard from '@/modules/runs/presentation/components/RunJobCard.vue'
import EmptyState from '@/shared/components/EmptyState.vue'
import { cn } from '@/shared/utils/cn'

defineProps<{
  jobs: RunJob[]
  failures: RunFailure[]
  error: string | null
  selectedIndex: number
}>()
const emit = defineEmits<{ select: [index: number]; json: [index: number] }>()

const SPLIT_CLASS = 'lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]'
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
      <ul aria-label="Jobs" class="flex min-w-0 flex-col gap-3">
        <li v-for="(job, index) in jobs" :key="`${job.url ?? ''}-${index}`" data-slot="job-row">
          <RunJobCard
            :job="job"
            :is-selected="Boolean($slots.aside) && index === selectedIndex"
            :is-json-in-dialog="!$slots.aside"
            @select="emit('select', index)"
            @json="emit('json', index)"
          />
        </li>
      </ul>
      <aside
        v-if="$slots.aside"
        data-slot="job-aside"
        aria-label="Selected job JSON"
        class="sticky top-20 h-[calc(100dvh-6rem)] min-h-0 min-w-0"
      >
        <slot name="aside" />
      </aside>
    </div>
  </div>
</template>

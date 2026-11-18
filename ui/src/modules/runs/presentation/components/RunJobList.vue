<script setup lang="ts">
import type { RunFailure, RunJob } from '@/modules/runs/domain/entities/Run'
import EmptyState from '@/shared/components/EmptyState.vue'
import { Badge } from '@/shared/components/ui/badge'

defineProps<{ jobs: RunJob[]; failures: RunFailure[]; error: string | null }>()

function jobMeta(job: RunJob): string {
  return [job.company, job.location, job.postedAt]
    .filter((part): part is string => Boolean(part))
    .join(' · ')
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
    <ul v-else class="flex flex-col divide-y divide-line rounded-md border border-line">
      <li
        v-for="(job, index) in jobs"
        :key="`${job.url ?? ''}-${index}`"
        data-slot="job-row"
        class="flex items-start justify-between gap-3 p-4"
      >
        <div class="flex min-w-0 flex-col gap-1">
          <a
            v-if="job.url"
            :href="job.url"
            target="_blank"
            rel="noopener noreferrer"
            class="w-fit text-body font-semibold text-link hover:underline focus-visible:focus-ring"
          >
            {{ job.title ?? 'Untitled job' }}
            <span class="sr-only">(opens in new tab)</span>
          </a>
          <p v-else class="text-body font-semibold text-ink">{{ job.title ?? 'Untitled job' }}</p>
          <p v-if="jobMeta(job)" class="text-body-sm text-ink-muted">{{ jobMeta(job) }}</p>
        </div>
        <Badge v-if="job.site" data-slot="job-site">{{ job.site }}</Badge>
      </li>
    </ul>
  </div>
</template>

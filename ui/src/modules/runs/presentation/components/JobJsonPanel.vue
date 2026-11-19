<script setup lang="ts">
import { computed } from 'vue'
import type { RunJob } from '@/modules/runs/domain/entities/Run'
import JsonViewer from '@/modules/runs/presentation/components/JsonViewer.vue'
import { toJobJsonLabel, toJobTitle } from '@/modules/runs/presentation/components/jobJsonLabels'

const props = defineProps<{ job: RunJob | null }>()
const emit = defineEmits<{ fullscreen: [] }>()

const title = computed(() => toJobTitle(props.job))
const label = computed(() => toJobJsonLabel(props.job))
</script>

<template>
  <div data-slot="job-json-panel" class="flex h-full min-h-0 min-w-0 flex-col gap-2">
    <template v-if="job">
      <header data-slot="json-header" class="flex min-w-0 items-baseline gap-2">
        <h4 class="shrink-0 text-caption text-ink">JSON</h4>
        <p data-slot="json-job-title" class="min-w-0 truncate text-body-sm text-ink-muted">
          {{ title }}
        </p>
      </header>
      <JsonViewer :value="job.json" :label="label" @fullscreen="emit('fullscreen')" />
    </template>
    <p
      v-else
      data-slot="json-empty"
      class="flex min-h-32 flex-1 items-center justify-center rounded-lg border border-dashed border-line-strong p-6 text-center text-body-sm text-ink-muted"
    >
      Select a job to see its JSON
    </p>
  </div>
</template>

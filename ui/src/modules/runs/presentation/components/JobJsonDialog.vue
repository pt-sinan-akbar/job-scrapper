<script setup lang="ts">
import { computed } from 'vue'
import type { RunJob } from '@/modules/runs/domain/entities/Run'
import JsonViewer from '@/modules/runs/presentation/components/JsonViewer.vue'
import { toJobJsonLabel, toJobTitle } from '@/modules/runs/presentation/components/jobJsonLabels'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'

const props = defineProps<{ job: RunJob | null }>()
const isOpen = defineModel<boolean>('open', { default: false })

const title = computed(() => toJobTitle(props.job))
const label = computed(() => toJobJsonLabel(props.job))
</script>

<template>
  <Dialog v-model:open="isOpen">
    <DialogContent
      data-slot="job-json-dialog"
      class="inset-x-[2.5vw] h-[90dvh] max-h-[90dvh] max-w-none overflow-hidden p-4 sm:p-6"
    >
      <DialogHeader class="min-w-0">
        <DialogTitle class="truncate">{{ title }}</DialogTitle>
        <DialogDescription class="sr-only">Full JSON of this job</DialogDescription>
      </DialogHeader>
      <JsonViewer v-if="job" :value="job.json" :label="label" is-fullscreen-hidden />
      <p
        v-else
        data-slot="json-empty"
        class="flex flex-1 items-center justify-center rounded-lg border border-dashed border-line-strong p-6 text-center text-body-sm text-ink-muted"
      >
        No job selected
      </p>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { RunDetail } from '@/modules/runs/domain/entities/Run'
import RunJobList from '@/modules/runs/presentation/components/RunJobList.vue'
import RunJsonPanel from '@/modules/runs/presentation/components/RunJsonPanel.vue'
import RunResultsSkeleton from '@/modules/runs/presentation/components/RunResultsSkeleton.vue'
import {
  isResultsTab,
  readResultsTab,
  writeResultsTab,
  type ResultsTab,
} from '@/modules/runs/presentation/components/resultsTabStorage'
import PageSection from '@/shared/components/PageSection.vue'
import { Button } from '@/shared/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'

const props = defineProps<{
  detail: RunDetail | null
  isPending: boolean
  isLost?: boolean
  errorMessage: string | null
}>()
const emit = defineEmits<{ retry: [] }>()

const tab = ref<ResultsTab>(readResultsTab())

const summary = computed(() => {
  if (props.isLost || props.isPending || props.detail === null) {
    return undefined
  }
  const { keywords, sites } = props.detail.record
  return `${keywords.join(', ')} on ${sites.join(', ')}`
})

function changeTab(next: string | number): void {
  if (isResultsTab(next)) {
    tab.value = next
    writeResultsTab(next)
  }
}
</script>

<template>
  <PageSection title="Results" :description="summary">
    <p
      v-if="isLost"
      data-slot="results-lost"
      role="status"
      class="rounded-lg border border-dashed border-line-strong p-6 text-center text-body-sm text-ink-muted"
    >
      Lost track of this run. Reload to check it.
    </p>
    <RunResultsSkeleton v-else-if="isPending" />
    <Tabs v-else-if="detail" :model-value="tab" @update:model-value="changeTab">
      <TabsList aria-label="Result views">
        <TabsTrigger value="jobs">Jobs</TabsTrigger>
        <TabsTrigger value="json">JSON</TabsTrigger>
      </TabsList>
      <TabsContent value="jobs">
        <RunJobList :jobs="detail.jobs" :failures="detail.failures" :error="detail.record.error" />
      </TabsContent>
      <TabsContent value="json">
        <RunJsonPanel :key="detail.record.id" :payloads="detail.payloads" />
      </TabsContent>
    </Tabs>
    <div
      v-else-if="errorMessage"
      data-slot="results-error"
      role="alert"
      class="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line-strong p-4"
    >
      <div class="flex min-w-0 flex-col">
        <p class="text-body font-semibold text-ink">Could not load the latest run</p>
        <p class="text-body-sm text-ink-muted">{{ errorMessage }}</p>
      </div>
      <Button size="sm" @click="emit('retry')">Try again</Button>
    </div>
  </PageSection>
</template>

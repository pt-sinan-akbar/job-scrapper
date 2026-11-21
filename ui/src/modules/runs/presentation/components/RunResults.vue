<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import type { RunDetail } from '@/modules/runs/domain/entities/Run'
import JobJsonDialog from '@/modules/runs/presentation/components/JobJsonDialog.vue'
import JobJsonPanel from '@/modules/runs/presentation/components/JobJsonPanel.vue'
import RunJobList from '@/modules/runs/presentation/components/RunJobList.vue'
import RunResultsSkeleton from '@/modules/runs/presentation/components/RunResultsSkeleton.vue'
import PageSection from '@/shared/components/PageSection.vue'
import { Button } from '@/shared/components/ui/button'

const WIDE_SCREEN_QUERY = '(min-width: 64rem)'
const FIRST_JOB_INDEX = 0

const props = defineProps<{
  detail: RunDetail | null
  isPending: boolean
  isLost?: boolean
  errorMessage: string | null
}>()
const emit = defineEmits<{ retry: [] }>()

const pickedIndex = ref(FIRST_JOB_INDEX)
const isDialogOpen = ref(false)
const isWideScreen = useMediaQuery(WIDE_SCREEN_QUERY)

const shownDetail = computed(() => (props.isLost || props.isPending ? null : props.detail))
const jobs = computed(() => shownDetail.value?.jobs ?? [])
const selectedIndex = computed(() =>
  pickedIndex.value < jobs.value.length ? pickedIndex.value : FIRST_JOB_INDEX,
)
const selectedJob = computed(() => jobs.value[selectedIndex.value] ?? null)

const summary = computed(() => {
  if (shownDetail.value === null) {
    return undefined
  }
  const { keywords, sites } = shownDetail.value.record
  return `${keywords.join(', ')} on ${sites.join(', ')}`
})

watch(
  () => shownDetail.value?.record.id,
  () => {
    pickedIndex.value = FIRST_JOB_INDEX
    isDialogOpen.value = false
  },
)

watch(
  () => jobs.value.length,
  (count) => {
    if (pickedIndex.value >= count) {
      pickedIndex.value = FIRST_JOB_INDEX
    }
  },
)

function showJobJson(index: number): void {
  pickedIndex.value = index
  if (!isWideScreen.value) {
    isDialogOpen.value = true
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
    <template v-else-if="shownDetail">
      <RunJobList
        :jobs="shownDetail.jobs"
        :failures="shownDetail.failures"
        :error="shownDetail.record.error"
        :selected-index="selectedIndex"
        @select="showJobJson"
      >
        <template v-if="isWideScreen" #aside>
          <JobJsonPanel :job="selectedJob" @fullscreen="isDialogOpen = true" />
        </template>
      </RunJobList>
      <JobJsonDialog v-model:open="isDialogOpen" :job="selectedJob" />
    </template>
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

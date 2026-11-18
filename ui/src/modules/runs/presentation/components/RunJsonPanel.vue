<script setup lang="ts">
import { computed, ref } from 'vue'
import type { JsonValue, RunPayload } from '@/modules/runs/domain/entities/Run'
import JsonViewer from '@/modules/runs/presentation/components/JsonViewer.vue'
import PayloadChips from '@/modules/runs/presentation/components/PayloadChips.vue'

type PayloadField = 'filtered' | 'raw'

const props = defineProps<{ payloads: RunPayload[] }>()

const FIELDS: readonly PayloadField[] = ['filtered', 'raw']
const TITLES: Record<PayloadField, string> = { filtered: 'Filtered', raw: 'Raw' }
const MISSING_NOTES: Record<PayloadField, string> = {
  filtered: 'Filtered data was not saved for this run',
  raw: 'Raw data was not saved for this run',
}

const pickedIndex = ref(0)
const effectiveIndex = computed(() =>
  pickedIndex.value < props.payloads.length ? pickedIndex.value : 0,
)
const picked = computed(() => props.payloads[effectiveIndex.value] ?? null)

function toJobCount(value: JsonValue): number | null {
  if (Array.isArray(value)) {
    return value.length
  }
  if (typeof value !== 'object' || value === null) {
    return null
  }
  const { count, jobs } = value
  if (typeof count === 'number' && Number.isFinite(count)) {
    return count
  }
  return Array.isArray(jobs) ? jobs.length : null
}
</script>

<template>
  <p
    v-if="picked === null"
    data-slot="json-missing"
    class="rounded-lg border border-dashed border-line-strong p-6 text-center text-body-sm text-ink-muted"
  >
    No JSON was saved for this run
  </p>
  <div v-else class="flex min-w-0 flex-col gap-8">
    <PayloadChips
      :payloads="payloads"
      :picked-index="effectiveIndex"
      @pick="pickedIndex = $event"
    />
    <div
      v-for="field in FIELDS"
      :key="field"
      :data-slot="`json-${field}`"
      class="flex min-w-0 flex-col gap-2"
    >
      <JsonViewer
        v-if="picked[field] !== null"
        :title="TITLES[field]"
        :value="picked[field]"
        :job-count="toJobCount(picked[field])"
      />
      <template v-else>
        <h4 class="text-body font-semibold text-ink">{{ TITLES[field] }}</h4>
        <p
          data-slot="json-missing"
          class="rounded-lg border border-dashed border-line-strong p-6 text-center text-body-sm text-ink-muted"
        >
          {{ MISSING_NOTES[field] }}
        </p>
      </template>
    </div>
  </div>
</template>

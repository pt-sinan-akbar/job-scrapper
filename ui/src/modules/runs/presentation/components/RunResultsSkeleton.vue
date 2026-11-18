<script setup lang="ts">
import { Skeleton } from '@/shared/components/ui/skeleton'

const ROW_COUNT = 3
</script>

<template>
  <div
    data-slot="results-skeleton"
    role="status"
    aria-busy="true"
    class="flex min-w-0 flex-col gap-4"
  >
    <span class="sr-only">Loading results</span>
    <div class="flex gap-2 border-b border-line pb-2">
      <Skeleton class="h-8 w-16" />
      <Skeleton class="h-8 w-16" />
    </div>
    <div class="flex flex-col divide-y divide-line rounded-md border border-line">
      <div v-for="row in ROW_COUNT" :key="row" class="flex items-start justify-between gap-3 p-4">
        <div class="flex min-w-0 flex-1 flex-col gap-2">
          <Skeleton class="h-5 w-2/3" />
          <Skeleton class="h-4 w-1/2" />
        </div>
        <Skeleton class="h-6 w-16 rounded-full" />
      </div>
    </div>
  </div>
</template>
